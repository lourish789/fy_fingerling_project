"""
Passwords, tokens, Google ID-token verification and rate limiting.

Token model
-----------
* Access token: HS256 JWT, 15 minutes, sent as `Authorization: Bearer`. The
  browser keeps it in memory only.
* Refresh token: 256-bit random string in an httpOnly cookie scoped to
  /api/auth. Only its SHA-256 is stored. Rotated on every use.
* Media token: short JWT for a single run's files or the MJPEG feed, so an
  <img src> or a download link can be authorised without a header.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import threading
import time
from collections import deque
from datetime import timedelta
from typing import Any, Deque, Dict, Optional, Tuple

import jwt
from werkzeug.security import check_password_hash, generate_password_hash

from api.db import utcnow

ISSUER = 'aquacount'
AUDIENCE = 'aquacount-api'
EMAIL_RE = re.compile(r'^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$')

# A real hash, so a sign-in for an unknown email costs the same time as a wrong password.
_DUMMY_HASH = generate_password_hash('aquacount-timing-equaliser')


# ── Passwords ────────────────────────────────────────────────────────────────
def hash_password(password: str) -> str:
    return generate_password_hash(password)  # scrypt (Werkzeug 3 default)


def verify_password(password_hash: Optional[str], password: str) -> bool:
    if not password_hash:
        check_password_hash(_DUMMY_HASH, password)
        return False
    return check_password_hash(password_hash, password)


def password_problem(password: str, email: str = '') -> Optional[str]:
    """Length-based policy (NIST 800-63B): long beats complicated."""
    if not isinstance(password, str) or len(password) < 8:
        return 'Use at least 8 characters.'
    if len(password) > 128:
        return 'Use at most 128 characters.'
    if email and password.strip().lower() == email.strip().lower():
        return 'Your password cannot be your email address.'
    if len(set(password)) < 4:
        return 'That password is too easy to guess.'
    return None


def normalise_email(email: Any) -> str:
    return str(email or '').strip().lower()


def valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match(email)) and len(email) <= 254


# ── Opaque tokens ────────────────────────────────────────────────────────────
def new_opaque_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


# ── JWTs ─────────────────────────────────────────────────────────────────────
class TokenService:
    def __init__(self, secret: str, access_minutes: int = 15, media_minutes: int = 15):
        if len(secret) < 32:
            raise ValueError('JWT secret must be at least 32 characters')
        self._secret = secret
        self.access_ttl = timedelta(minutes=access_minutes)
        self.media_ttl = timedelta(minutes=media_minutes)

    def _encode(self, claims: Dict[str, Any], ttl: timedelta) -> str:
        now = int(time.time())
        payload = {'iss': ISSUER, 'aud': AUDIENCE, 'iat': now,
                   'exp': now + int(ttl.total_seconds()), **claims}
        return jwt.encode(payload, self._secret, algorithm='HS256')

    def issue_access(self, user_public_id: str, session_id: str, role: str) -> Tuple[str, int]:
        token = self._encode({'sub': user_public_id, 'sid': session_id, 'role': role,
                              'typ': 'access'}, self.access_ttl)
        return token, int(self.access_ttl.total_seconds())

    def issue_media(self, user_public_id: str, scope: str) -> str:
        return self._encode({'sub': user_public_id, 'scope': scope, 'typ': 'media'}, self.media_ttl)

    def decode(self, token: str, typ: str) -> Dict[str, Any]:
        claims = jwt.decode(token, self._secret, algorithms=['HS256'], audience=AUDIENCE,
                            issuer=ISSUER, leeway=10,
                            options={'require': ['exp', 'iat', 'sub', 'typ']})
        if claims.get('typ') != typ:
            raise jwt.InvalidTokenError('wrong token type')
        return claims


# ── Google Identity Services ─────────────────────────────────────────────────
class GoogleVerificationError(Exception):
    pass


class GoogleVerifier:
    """Verifies the ID token ("credential") returned by the Sign in with Google button."""
    CERTS_URL = 'https://www.googleapis.com/oauth2/v3/certs'
    ISSUERS = ('accounts.google.com', 'https://accounts.google.com')

    def __init__(self, client_id: str):
        self.client_id = client_id
        self._jwks = jwt.PyJWKClient(self.CERTS_URL, cache_keys=True, lifespan=3600,
                                     timeout=10) if client_id else None

    def verify(self, credential: str) -> Dict[str, Any]:
        if not self._jwks:
            raise GoogleVerificationError('Google sign-in is not configured on this server.')
        try:
            key = self._jwks.get_signing_key_from_jwt(credential)
            claims = jwt.decode(credential, key.key, algorithms=['RS256'],
                                audience=self.client_id, leeway=30,
                                options={'require': ['exp', 'iat', 'sub', 'iss', 'aud']})
        except jwt.PyJWKClientError as e:
            raise GoogleVerificationError('Could not reach Google to verify the sign-in.') from e
        except jwt.InvalidTokenError as e:
            raise GoogleVerificationError('The Google sign-in was invalid or has expired.') from e
        if claims.get('iss') not in self.ISSUERS:
            raise GoogleVerificationError('The Google sign-in came from an unexpected issuer.')
        if not claims.get('email') or not claims.get('email_verified'):
            raise GoogleVerificationError('Your Google account email is not verified.')
        return claims


# ── Rate limiting ────────────────────────────────────────────────────────────
class RateLimiter:
    """
    In-memory sliding-window limiter. Enough for one gunicorn worker (Render)
    or the hatchery laptop; use Redis-backed limits if you scale out.
    """

    def __init__(self):
        self._hits: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()
        self._calls = 0

    def _window(self, key: str, window: float, now: float) -> Deque[float]:
        q = self._hits.setdefault(key, deque())
        while q and q[0] <= now - window:
            q.popleft()
        return q

    def hit(self, key: str, limit: int, window: float) -> Tuple[bool, int]:
        """Record one attempt. Returns (allowed, retry_after_seconds)."""
        now = time.monotonic()
        with self._lock:
            self._maybe_gc(now)
            q = self._window(key, window, now)
            if len(q) >= limit:
                return False, max(1, int(q[0] + window - now + 0.999))
            q.append(now)
            return True, 0

    def blocked(self, key: str, limit: int, window: float) -> Tuple[bool, int]:
        """Check without recording (used for counting only failed sign-ins)."""
        now = time.monotonic()
        with self._lock:
            q = self._window(key, window, now)
            if len(q) >= limit:
                return True, max(1, int(q[0] + window - now + 0.999))
            return False, 0

    def record(self, key: str) -> None:
        with self._lock:
            self._hits.setdefault(key, deque()).append(time.monotonic())

    def clear(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)

    def _maybe_gc(self, now: float, horizon: float = 3600.0) -> None:
        self._calls += 1
        if self._calls % 500:
            return
        stale = [k for k, q in self._hits.items() if not q or q[-1] < now - horizon]
        for k in stale:
            del self._hits[k]


def refresh_expiry(persistent: bool, refresh_days: int, session_hours: int):
    return utcnow() + (timedelta(days=refresh_days) if persistent else timedelta(hours=session_hours))
