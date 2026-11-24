"""
Authenticated web layer for AquaCount.

`init_api(app, server)` adds accounts, sessions, per-user run history,
insights and admin endpoints to the streaming server's Flask app, puts every
/api route and the MJPEG feed behind sign-in, and serves the PWA build from
web/dist.
"""

from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from typing import Any, Optional, Tuple

import jwt
from flask import Flask, Response, g, request, send_from_directory
from sqlalchemy import select
from werkzeug.security import safe_join

from api.config import APP_VERSION, WebConfig
from api.context import ApiContext
from api.db import Database, User
from api.http import error, public
from api.routes_admin import bp as admin_bp
from api.routes_auth import bp as auth_bp
from api.routes_me import bp as me_bp
from api.routes_runs import bp as runs_bp, persist_run

__all__ = ['init_api', 'ApiContext', 'WebConfig', 'APP_VERSION', 'authenticate_token']

# Windows can map .js to text/plain in the registry, which breaks ES modules.
for _type, _ext in (('application/javascript', '.js'), ('application/javascript', '.mjs'),
                    ('text/css', '.css'), ('application/manifest+json', '.webmanifest'),
                    ('image/svg+xml', '.svg'), ('font/woff2', '.woff2'), ('application/json', '.json')):
    mimetypes.add_type(_type, _ext)


def authenticate_token(c: ApiContext, token: str, typ: str = 'access') -> Tuple[Optional[User], Optional[dict], str]:
    """Validate a bearer/media token. Returns (user, claims, error_code)."""
    if not token:
        return None, None, 'unauthorized'
    try:
        claims = c.tokens.decode(token, typ)
    except jwt.ExpiredSignatureError:
        return None, None, 'token_expired'
    except jwt.InvalidTokenError:
        return None, None, 'invalid_token'
    with c.db.session() as s:
        user = s.scalar(select(User).where(User.public_id == claims['sub']))
        if user is None or not user.is_active:
            return None, None, 'unauthorized'
        if typ == 'access' and not c.family_active(s, str(claims.get('sid') or '')):
            return None, None, 'session_revoked'
    return user, claims, ''


def _media_scope_allows(scope: str, path: str) -> bool:
    if scope == 'stream':
        return path == '/video_feed'
    if scope.startswith('run:'):
        return path.startswith(f'/api/runs/{scope[4:]}/')
    return False


def _install_guard(app: Flask, c: ApiContext) -> None:
    @app.before_request
    def _require_sign_in():
        g.user = None
        g.claims = {}
        path = request.path
        if request.method == 'OPTIONS':
            return None
        if not (path.startswith('/api/') or path == '/video_feed'):
            return None
        view = app.view_functions.get(request.endpoint) if request.endpoint else None
        if view is not None and getattr(view, '_aquacount_public', False):
            return None

        header = request.headers.get('Authorization', '')
        if header[:7].lower() == 'bearer ':
            user, claims, code = authenticate_token(c, header[7:].strip(), 'access')
        elif request.method == 'GET' and request.args.get('t'):
            user, claims, code = authenticate_token(c, request.args['t'], 'media')
            if user is not None and not _media_scope_allows(str(claims.get('scope', '')), path):
                user, code = None, 'forbidden'
        else:
            user, claims, code = None, None, 'unauthorized'

        if user is None:
            messages = {'token_expired': 'Your session needs refreshing.',
                        'session_revoked': 'This session was signed out.'}
            return error(messages.get(code, 'Sign in to continue.'), 401, code)
        g.user = user
        g.claims = claims or {}
        return None

    @app.after_request
    def _headers(resp: Response):
        resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
        resp.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        if request.path.startswith('/api/') and 'Cache-Control' not in resp.headers:
            resp.headers['Cache-Control'] = 'no-store'
        return resp

    @app.errorhandler(413)
    def _too_large(_e):
        return error('That file is too large (500 MB maximum).', 413)


def _register_health(app: Flask, server: Any) -> None:
    @app.get('/api/health')
    @public
    def health():
        return {'status': 'ok', 'version': APP_VERSION,
                'model_loaded': getattr(server, 'counter', None) is not None}


def _register_spa(app: Flask, dist: Path) -> None:
    """Serve the PWA build: hashed assets cached for a year, the shell and service worker never."""

    def _not_built():
        return Response(
            '<!doctype html><meta charset="utf-8"><title>AquaCount</title>'
            '<body style="font:16px system-ui;max-width:560px;margin:48px auto;padding:0 16px">'
            '<h1>AquaCount API is running</h1><p>The web app has not been built yet. Run:</p>'
            '<pre>cd web\nnpm ci\nnpm run build</pre><p>then reload this page.</p>',
            status=503, mimetype='text/html')

    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    def spa(path: str):
        if path.startswith(('api/', 'socket.io')):
            return error('Not found.', 404)
        if not (dist / 'index.html').is_file():
            return _not_built()
        if path:
            target = safe_join(str(dist), path)
            if target and os.path.isfile(target):
                resp = send_from_directory(dist, path)
                if path.startswith('assets/'):
                    resp.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
                elif path in ('sw.js', 'manifest.webmanifest', 'registerSW.js') or path.startswith('workbox-'):
                    resp.headers['Cache-Control'] = 'no-cache'
                return resp
            if '.' in path.rsplit('/', 1)[-1]:
                return error('Not found.', 404)  # a missing file, not an app route
        resp = send_from_directory(dist, 'index.html')
        resp.headers['Cache-Control'] = 'no-cache'
        resp.headers['X-Frame-Options'] = 'DENY'
        return resp


def init_api(app: Flask, server: Any = None, database_url: Optional[str] = None,
             config: Optional[WebConfig] = None, google_verifier: Any = None,
             serve_spa: bool = True) -> ApiContext:
    cfg = config or WebConfig.from_env(database_url=database_url)
    c = ApiContext(cfg, Database(cfg.database_url), server, google_verifier)
    app.extensions['aquacount_api'] = c

    for bp in (auth_bp, me_bp, runs_bp, admin_bp):
        app.register_blueprint(bp)
    _register_health(app, server)
    _install_guard(app, c)
    if serve_spa:
        _register_spa(app, cfg.web_dist)

    if server is not None:
        server.on_run_saved = lambda summary, kind, owner_id: persist_run(c, summary, kind, owner_id)
    return c
