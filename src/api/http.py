"""Small HTTP helpers shared by the API blueprints."""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable, Dict, Optional

from flask import current_app, g, jsonify, request

from api.context import request_ip


def ctx():
    """The ApiContext attached to the running Flask app."""
    return current_app.extensions['aquacount_api']


def error(message: str, status: int, code: Optional[str] = None, **extra: Any):
    body: Dict[str, Any] = {'error': message, 'code': code or _default_code(status)}
    body.update(extra)
    resp = jsonify(body)
    resp.status_code = status
    return resp


def _default_code(status: int) -> str:
    return {400: 'bad_request', 401: 'unauthorized', 403: 'forbidden', 404: 'not_found',
            409: 'conflict', 413: 'too_large', 429: 'rate_limited'}.get(status, 'error')


def json_body() -> Dict[str, Any]:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def client_ip() -> str:
    return request_ip(ctx().cfg) or 'unknown'


def public(fn: Callable) -> Callable:
    """Mark a view as reachable without signing in (everything under /api is private by default)."""
    fn._aquacount_public = True  # type: ignore[attr-defined]
    return fn


def current_user():
    return getattr(g, 'user', None)


def require_role(role: str) -> Callable:
    def deco(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = current_user()
            if user is None:
                return error('Sign in to continue.', 401)
            if user.role != role:
                return error('You do not have permission to do that.', 403)
            return fn(*args, **kwargs)
        return wrapper
    return deco


def rate_limit(name: str, limit: int, window: float, by: str = 'ip') -> Callable:
    """Reject with 429 + Retry-After once `limit` requests arrive within `window` seconds."""
    def deco(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = current_user()
            ident = user.public_id if (by == 'user' and user is not None) else client_ip()
            allowed, retry = ctx().limiter.hit(f'{name}:{ident}', limit, window)
            if not allowed:
                return too_many(retry)
            return fn(*args, **kwargs)
        # keep the public marker if the view had one
        if getattr(fn, '_aquacount_public', False):
            wrapper._aquacount_public = True  # type: ignore[attr-defined]
        return wrapper
    return deco


def too_many(retry_after: int, message: Optional[str] = None):
    resp = error(message or f'Too many attempts. Try again in {retry_after} s.', 429,
                 retry_after=retry_after)
    resp.headers['Retry-After'] = str(retry_after)
    return resp
