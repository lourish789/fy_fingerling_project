"""
Persistence for users, sign-in sessions, password resets and run ownership.

SQLite (the default, file in `instance/`) for the hatchery laptop and local
development; any SQLAlchemy URL via DATABASE_URL for the cloud. Render's free
tier wipes its disk on every restart, so a hosted deployment needs Postgres.

Tables are created on start-up. Adding columns later needs a migration
(Alembic); see docs/WEB_APP.md.
"""

from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

from sqlalchemy import (Boolean, DateTime, Float, ForeignKey, Integer, String, Text,
                        create_engine, event)
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool


def utcnow() -> datetime:
    """Naive UTC: SQLite drops tz info, so everything is stored and compared as naive UTC."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat(timespec='seconds') + 'Z' if dt else None


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[str] = mapped_column(String(32), unique=True, index=True,
                                           default=lambda: uuid.uuid4().hex)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), default='')
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    google_sub: Mapped[Optional[str]] = mapped_column(String(64), unique=True, nullable=True)
    google_email: Mapped[Optional[str]] = mapped_column(String(254), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    role: Mapped[str] = mapped_column(String(16), default='operator')
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    onboarded: Mapped[bool] = mapped_column(Boolean, default=False)
    preferences_json: Mapped[str] = mapped_column(Text, default='{}')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    password_changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    @property
    def preferences(self) -> Dict[str, Any]:
        try:
            value = json.loads(self.preferences_json or '{}')
            return value if isinstance(value, dict) else {}
        except ValueError:
            return {}

    @preferences.setter
    def preferences(self, value: Dict[str, Any]) -> None:
        self.preferences_json = json.dumps(value, separators=(',', ':'))

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.public_id,
            'email': self.email,
            'name': self.name,
            'avatar_url': self.avatar_url,
            'role': self.role,
            'has_password': bool(self.password_hash),
            'google_connected': bool(self.google_sub),
            'google_email': self.google_email,
            'onboarded': bool(self.onboarded),
            'preferences': self.preferences,
            'created_at': iso(self.created_at),
            'last_login_at': iso(self.last_login_at),
        }


class RefreshToken(Base):
    """
    One row per issued refresh token. Tokens sharing a `family_id` are one
    sign-in session: each refresh rotates the token, and presenting an already
    rotated token (outside a short grace window) revokes the whole family.
    """
    __tablename__ = 'refresh_tokens'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    family_id: Mapped[str] = mapped_column(String(32), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    persistent: Mapped[bool] = mapped_column(Boolean, default=True)
    family_created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    rotated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    user_agent: Mapped[str] = mapped_column(String(255), default='')
    ip: Mapped[str] = mapped_column(String(64), default='')


class PasswordReset(Base):
    __tablename__ = 'password_resets'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class RunRecord(Base):
    """
    Who started a run, plus its headline numbers for fast history and insights.
    The full audit trail stays on disk in output/runs/<run_id>/.
    """
    __tablename__ = 'runs'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'),
                                                   index=True, nullable=True)
    kind: Mapped[str] = mapped_column(String(16), default='video')
    source: Mapped[str] = mapped_column(String(255), default='')
    status: Mapped[str] = mapped_column(String(24), default='completed')
    total: Mapped[int] = mapped_column(Integer, default=0)
    counts_json: Mapped[str] = mapped_column(Text, default='{}')
    corrected_total: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    correction_factor: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    warning: Mapped[str] = mapped_column(Text, default='')
    frames_processed: Mapped[int] = mapped_column(Integer, default=0)
    processing_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    @property
    def counts(self) -> Dict[str, int]:
        try:
            value = json.loads(self.counts_json or '{}')
            return {str(k): int(v or 0) for k, v in value.items()} if isinstance(value, dict) else {}
        except (ValueError, TypeError):
            return {}

    def to_dict(self, owner: Optional[User] = None) -> Dict[str, Any]:
        return {
            'run_id': self.run_id,
            'kind': self.kind,
            'source': self.source,
            'status': self.status,
            'total': self.total,
            'counts': self.counts,
            'corrected_total': self.corrected_total,
            'correction_factor': self.correction_factor,
            'warning': self.warning,
            'frames_processed': self.frames_processed,
            'processing_seconds': self.processing_seconds,
            'started_at': iso(self.started_at),
            'ended_at': iso(self.ended_at),
            'created_at': iso(self.created_at),
            'owner': ({'id': owner.public_id, 'name': owner.name or owner.email} if owner else None),
        }


def _normalise_url(url: str) -> str:
    # Heroku/Render/Neon style URLs use the scheme SQLAlchemy dropped in 1.4.
    if url.startswith('postgres://'):
        return 'postgresql://' + url[len('postgres://'):]
    return url


class Database:
    def __init__(self, url: str):
        url = _normalise_url(url)
        parsed = make_url(url)
        kwargs: Dict[str, Any] = {'future': True}

        self.is_sqlite = parsed.get_backend_name() == 'sqlite'
        if self.is_sqlite:
            kwargs['connect_args'] = {'check_same_thread': False, 'timeout': 15}
            if not parsed.database or parsed.database == ':memory:':
                kwargs['poolclass'] = StaticPool
            else:
                Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)
        else:
            kwargs.update(pool_pre_ping=True, pool_size=5, max_overflow=5, pool_recycle=300)

        self.engine = create_engine(url, **kwargs)
        self.backend = parsed.get_backend_name()

        if self.is_sqlite:
            @event.listens_for(self.engine, 'connect')
            def _sqlite_pragmas(dbapi_conn, _record):
                cur = dbapi_conn.cursor()
                cur.execute('PRAGMA foreign_keys=ON')
                if parsed.database and parsed.database != ':memory:':
                    cur.execute('PRAGMA journal_mode=WAL')
                cur.close()

        Base.metadata.create_all(self.engine)
        self._Session = sessionmaker(self.engine, expire_on_commit=False)

    @contextmanager
    def session(self) -> Iterator[Session]:
        s = self._Session()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    def dispose(self) -> None:
        self.engine.dispose()
