"""
Settings for the authenticated web layer, read from environment variables.

Everything has a working default for the offline hatchery laptop (SQLite in
`instance/`, secret persisted in `instance/secret_key`, no email, no Google).
Cloud deployments set the variables listed in `.env.example`.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import FrozenSet

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTANCE_DIR = REPO_ROOT / 'instance'
APP_VERSION = '2.0.0'


def load_dotenv(path: Path = REPO_ROOT / '.env') -> None:
    """Fill unset environment variables from KEY=VALUE lines in .env (real env vars win)."""
    try:
        lines = path.read_text(encoding='utf-8').splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value


def _env(name: str, default: str = '') -> str:
    return os.environ.get(name, default).strip()


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name)
    if not raw:
        return default
    return raw.lower() in ('1', 'true', 'yes', 'on')


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name) or default)
    except ValueError:
        return default


def _load_or_create_secret() -> str:
    """JWT signing key: env var, else a key persisted on disk so tokens survive restarts."""
    secret = _env('JWT_SECRET') or _env('FLASK_SECRET_KEY')
    if secret:
        return secret
    path = INSTANCE_DIR / 'secret_key'
    try:
        if path.exists():
            stored = path.read_text(encoding='utf-8').strip()
            if len(stored) >= 32:
                return stored
        INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
        stored = secrets.token_urlsafe(48)
        path.write_text(stored, encoding='utf-8')
        return stored
    except OSError:
        # Read-only disk: tokens will not survive a restart, but sign-in still works.
        return secrets.token_urlsafe(48)


@dataclass(frozen=True)
class WebConfig:
    database_url: str
    jwt_secret: str
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    session_refresh_hours: int = 24          # "keep me signed in" unticked
    refresh_reuse_grace_seconds: int = 30    # two tabs refreshing at once is not theft
    media_token_minutes: int = 15
    google_client_id: str = ''
    allow_signup: bool = True
    admin_emails: FrozenSet[str] = field(default_factory=frozenset)
    cookie_samesite: str = 'Lax'
    cookie_secure: str = 'auto'              # auto | always | never
    trust_proxy: bool = False
    app_url: str = ''
    smtp_host: str = ''
    smtp_port: int = 587
    smtp_user: str = ''
    smtp_password: str = ''
    smtp_from: str = ''
    smtp_security: str = 'starttls'          # starttls | ssl | none
    web_dist: Path = REPO_ROOT / 'web' / 'dist'

    @property
    def email_enabled(self) -> bool:
        return bool(self.smtp_host and self.smtp_from)

    @property
    def google_enabled(self) -> bool:
        return bool(self.google_client_id)

    @classmethod
    def from_env(cls, **overrides) -> 'WebConfig':
        samesite = _env('REFRESH_COOKIE_SAMESITE', 'Lax').capitalize()
        if samesite not in ('Lax', 'Strict', 'None'):
            samesite = 'Lax'
        cfg = cls(
            database_url=_env('DATABASE_URL') or f"sqlite:///{(INSTANCE_DIR / 'aquacount.db').as_posix()}",
            jwt_secret=_load_or_create_secret(),
            access_token_minutes=_env_int('ACCESS_TOKEN_MINUTES', 15),
            refresh_token_days=_env_int('REFRESH_TOKEN_DAYS', 30),
            google_client_id=_env('GOOGLE_CLIENT_ID'),
            allow_signup=_env_bool('ALLOW_SIGNUP', True),
            admin_emails=frozenset(e.strip().lower() for e in _env('ADMIN_EMAILS').split(',') if e.strip()),
            cookie_samesite=samesite,
            cookie_secure=(_env('REFRESH_COOKIE_SECURE', 'auto').lower() or 'auto'),
            trust_proxy=_env_bool('TRUST_PROXY', False),
            app_url=_env('APP_URL').rstrip('/'),
            smtp_host=_env('SMTP_HOST'),
            smtp_port=_env_int('SMTP_PORT', 587),
            smtp_user=_env('SMTP_USER'),
            smtp_password=_env('SMTP_PASSWORD'),
            smtp_from=_env('SMTP_FROM'),
            smtp_security=(_env('SMTP_SECURITY', 'starttls').lower() or 'starttls'),
            web_dist=Path(_env('WEB_DIST')) if _env('WEB_DIST') else REPO_ROOT / 'web' / 'dist',
        )
        overrides = {k: v for k, v in overrides.items() if v is not None}
        return replace(cfg, **overrides) if overrides else cfg
