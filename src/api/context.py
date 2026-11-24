"""Shared state for the API: config, database, token services, and session handling."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Dict, Optional, Tuple

from flask import Response, request
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from api.config import WebConfig
from api.db import Database, RefreshToken, User, utcnow
from api.security import (GoogleVerifier, RateLimiter, TokenService, new_opaque_token,
                          refresh_expiry, token_digest)

REFRESH_COOKIE = 'aq_refresh'
REFRESH_COOKIE_PATH = '/api/auth'


@dataclass
class RotateResult:
    ok: bool
    user: Optional[User] = None
    family_id: str = ''
    new_token: Optional[str] = None      # None during the grace window: keep the browser's cookie
    persistent: bool = True
    reason: str = ''


class ApiContext:
    def __init__(self, cfg: WebConfig, db: Database, server: Any = None,
                 google: Optional[GoogleVerifier] = None):
        self.cfg = cfg
        self.db = db
        self.server = server
        self.tokens = TokenService(cfg.jwt_secret, cfg.access_token_minutes, cfg.media_token_minutes)
        self.google = google or GoogleVerifier(cfg.google_client_id)
        self.limiter = RateLimiter()

    # ── Users ────────────────────────────────────────────────────────────────
    def role_for_new_user(self, s: Session, email: str) -> str:
        if email in self.cfg.admin_emails:
            return 'admin'
        has_admin = s.scalar(select(User.id).where(User.role == 'admin').limit(1))
        return 'operator' if has_admin else 'admin'  # first account administers the station

    # ── Sessions (refresh-token families) ────────────────────────────────────
    def create_session(self, s: Session, user: User, persistent: bool) -> Tuple[str, RefreshToken]:
        raw = new_opaque_token()
        now = utcnow()
        row = RefreshToken(
            user_id=user.id,
            family_id=uuid.uuid4().hex,
            token_hash=token_digest(raw),
            persistent=persistent,
            family_created_at=now,
            created_at=now,
            expires_at=refresh_expiry(persistent, self.cfg.refresh_token_days,
                                      self.cfg.session_refresh_hours),
            user_agent=(request.headers.get('User-Agent') or '')[:255],
            ip=request_ip(self.cfg),
        )
        s.add(row)
        user.last_login_at = now
        return raw, row

    def rotate(self, s: Session, raw: str) -> RotateResult:
        row = s.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_digest(raw)))
        now = utcnow()
        if row is None:
            return RotateResult(False, reason='unknown')
        user = s.get(User, row.user_id)
        if user is None or not user.is_active:
            return RotateResult(False, reason='inactive')
        if row.revoked_at is not None:
            return RotateResult(False, reason='revoked')
        if row.expires_at <= now:
            return RotateResult(False, reason='expired')

        if row.rotated_at is not None:
            if now - row.rotated_at <= timedelta(seconds=self.cfg.refresh_reuse_grace_seconds):
                # Another tab refreshed with this cookie a moment ago. The browser already
                # holds the newer cookie, so hand out an access token and leave it alone.
                if self.family_active(s, row.family_id):
                    return RotateResult(True, user, row.family_id, None, row.persistent)
                return RotateResult(False, reason='revoked')
            # An old token came back long after rotation: treat it as stolen.
            self.revoke_family(s, row.family_id)
            return RotateResult(False, reason='reuse')

        new_raw = new_opaque_token()
        row.rotated_at = now
        s.add(RefreshToken(
            user_id=user.id,
            family_id=row.family_id,
            token_hash=token_digest(new_raw),
            persistent=row.persistent,
            family_created_at=row.family_created_at,
            created_at=now,
            # Persistent sessions slide forward; browser-session ones keep their end time.
            expires_at=(refresh_expiry(True, self.cfg.refresh_token_days, 0)
                        if row.persistent else row.expires_at),
            user_agent=(request.headers.get('User-Agent') or row.user_agent or '')[:255],
            ip=request_ip(self.cfg),
        ))
        return RotateResult(True, user, row.family_id, new_raw, row.persistent)

    def family_active(self, s: Session, family_id: str) -> bool:
        now = utcnow()
        return s.scalar(
            select(RefreshToken.id).where(
                RefreshToken.family_id == family_id,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.rotated_at.is_(None),
                RefreshToken.expires_at > now,
            ).limit(1)
        ) is not None

    def family_for_token(self, s: Session, raw: str) -> Optional[RefreshToken]:
        return s.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_digest(raw)))

    def revoke_family(self, s: Session, family_id: str) -> None:
        s.execute(update(RefreshToken)
                  .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
                  .values(revoked_at=utcnow()))

    def revoke_all(self, s: Session, user_id: int, except_family: Optional[str] = None) -> None:
        stmt = update(RefreshToken).where(RefreshToken.user_id == user_id,
                                          RefreshToken.revoked_at.is_(None))
        if except_family:
            stmt = stmt.where(RefreshToken.family_id != except_family)
        s.execute(stmt.values(revoked_at=utcnow()))

    # ── Responses ────────────────────────────────────────────────────────────
    def auth_payload(self, user: User, family_id: str, **extra: Any) -> Dict[str, Any]:
        token, expires_in = self.tokens.issue_access(user.public_id, family_id, user.role)
        return {'access_token': token, 'token_type': 'Bearer', 'expires_in': expires_in,
                'user': user.to_dict(), **extra}

    def _cookie_secure(self) -> bool:
        mode = self.cfg.cookie_secure
        if mode in ('always', '1', 'true'):
            return True
        if mode in ('never', '0', 'false'):
            return False
        if request.is_secure:
            return True
        return self.cfg.trust_proxy and request.headers.get('X-Forwarded-Proto', '') == 'https'

    def set_refresh_cookie(self, resp: Response, raw: str, persistent: bool) -> None:
        secure = self._cookie_secure()
        samesite = self.cfg.cookie_samesite
        if samesite == 'None' and not secure:
            samesite = 'Lax'  # browsers drop SameSite=None cookies that are not Secure
        resp.set_cookie(
            REFRESH_COOKIE, raw,
            max_age=(self.cfg.refresh_token_days * 86400) if persistent else None,
            path=REFRESH_COOKIE_PATH, httponly=True, secure=secure, samesite=samesite,
        )

    def clear_refresh_cookie(self, resp: Response) -> None:
        resp.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH)


def request_ip(cfg: WebConfig) -> str:
    if cfg.trust_proxy:
        fwd = request.headers.get('X-Forwarded-For', '')
        if fwd:
            return fwd.split(',')[0].strip()[:64]
    return (request.remote_addr or '')[:64]
