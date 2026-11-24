"""
/api/auth: sign-up, sign-in (password or Google), session refresh, sign-out,
password reset, and linking a Google account to an existing one.
"""

from __future__ import annotations

from datetime import timedelta

from flask import Blueprint, jsonify, request
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from api.config import APP_VERSION
from api.context import REFRESH_COOKIE
from api.db import PasswordReset, User, utcnow
from api.http import ctx, current_user, error, json_body, public, rate_limit, too_many
from api.mailer import send_mail
from api.security import (GoogleVerificationError, hash_password, new_opaque_token,
                          normalise_email, password_problem, token_digest, valid_email,
                          verify_password)

bp = Blueprint('auth', __name__, url_prefix='/api/auth')

CSRF_HEADER = 'X-AquaCount-Client'
RESET_TTL = timedelta(minutes=30)


def _csrf_ok() -> bool:
    """Cookie-authenticated calls must carry a custom header, which a cross-site form cannot send."""
    return bool(request.headers.get(CSRF_HEADER))


def _issue(s, user: User, persistent: bool, status: int = 200, **extra):
    """Start a session for `user` inside the caller's DB session and build the response."""
    c = ctx()
    raw, row = c.create_session(s, user, persistent)
    s.flush()
    payload = c.auth_payload(user, row.family_id, **extra)
    resp = jsonify(payload)
    resp.status_code = status
    c.set_refresh_cookie(resp, raw, persistent)
    return resp


@bp.get('/config')
@public
def auth_config():
    c = ctx()
    return jsonify({
        'google_client_id': c.cfg.google_client_id or None,
        'signup_enabled': c.cfg.allow_signup,
        'password_reset': 'email' if c.cfg.email_enabled else 'console',
        'version': APP_VERSION,
    })


@bp.post('/signup')
@public
@rate_limit('signup', 10, 600)
def signup():
    c = ctx()
    if not c.cfg.allow_signup:
        return error('New accounts are turned off on this station. Ask an administrator.',
                     403, 'signup_disabled')
    data = json_body()
    name = str(data.get('name') or '').strip()[:120]
    email = normalise_email(data.get('email'))
    password = data.get('password') or ''
    remember = data.get('remember', True) is not False

    if not name:
        return error('Enter your name.', 400, 'invalid_name', field='name')
    if not valid_email(email):
        return error('Enter a valid email address.', 400, 'invalid_email', field='email')
    problem = password_problem(password, email)
    if problem:
        return error(problem, 400, 'weak_password', field='password')

    try:
        with c.db.session() as s:
            if s.scalar(select(User.id).where(User.email == email)):
                return error('An account with this email already exists. Sign in instead.',
                             409, 'email_taken', field='email')
            user = User(email=email, name=name, password_hash=hash_password(password),
                        role=c.role_for_new_user(s, email), password_changed_at=utcnow())
            s.add(user)
            s.flush()
            return _issue(s, user, remember, 201, is_new=True)
    except IntegrityError:
        return error('An account with this email already exists. Sign in instead.',
                     409, 'email_taken', field='email')


@bp.post('/login')
@public
@rate_limit('login', 20, 300)
def login():
    c = ctx()
    data = json_body()
    email = normalise_email(data.get('email'))
    password = data.get('password') or ''
    remember = data.get('remember', True) is not False
    if not email or not password:
        return error('Enter your email and password.', 400, 'missing_fields')

    fail_key = f'login-fail:{email}'
    blocked, retry = c.limiter.blocked(fail_key, 8, 900)
    if blocked:
        return too_many(retry, 'Too many failed sign-ins for this account. '
                               f'Try again in {max(1, retry // 60)} min, or reset your password.')

    with c.db.session() as s:
        user = s.scalar(select(User).where(User.email == email))
        if not verify_password(user.password_hash if user else None, password):
            c.limiter.record(fail_key)
            return error('Incorrect email or password. If you signed up with Google, '
                         'use Continue with Google.', 401, 'invalid_credentials')
        if not user.is_active:
            return error('This account has been deactivated. Contact the station administrator.',
                         403, 'account_disabled')
        c.limiter.clear(fail_key)
        return _issue(s, user, remember)


@bp.post('/google')
@public
@rate_limit('google', 20, 300)
def google_sign_in():
    c = ctx()
    if not c.cfg.google_enabled:
        return error('Google sign-in is not set up on this server.', 400, 'google_disabled')
    credential = str(json_body().get('credential') or '')
    if not credential:
        return error('Missing Google credential.', 400, 'missing_fields')
    try:
        claims = c.google.verify(credential)
    except GoogleVerificationError as e:
        return error(str(e), 401, 'google_invalid')

    sub = str(claims['sub'])
    email = normalise_email(claims.get('email'))
    with c.db.session() as s:
        user = s.scalar(select(User).where(User.google_sub == sub))
        is_new = False
        if user is None:
            if s.scalar(select(User.id).where(User.email == email)):
                # Never merge silently: whoever registered that email first must link it while signed in.
                return error('An account with this email already exists. Sign in with your password, '
                             'then connect Google from Profile → Connected accounts.',
                             409, 'account_exists')
            if not c.cfg.allow_signup:
                return error('New accounts are turned off on this station. Ask an administrator.',
                             403, 'signup_disabled')
            user = User(email=email, name=str(claims.get('name') or email.split('@')[0])[:120],
                        google_sub=sub, google_email=email,
                        avatar_url=(str(claims.get('picture'))[:512] if claims.get('picture') else None),
                        role=c.role_for_new_user(s, email))
            s.add(user)
            s.flush()
            is_new = True
        if not user.is_active:
            return error('This account has been deactivated. Contact the station administrator.',
                         403, 'account_disabled')
        if claims.get('picture') and not user.avatar_url:
            user.avatar_url = str(claims['picture'])[:512]
        return _issue(s, user, True, 201 if is_new else 200, is_new=is_new)


@bp.post('/refresh')
@public
@rate_limit('refresh', 60, 60)
def refresh():
    c = ctx()
    if not _csrf_ok():
        return error('Missing client header.', 403, 'csrf')
    raw = request.cookies.get(REFRESH_COOKIE)
    if not raw:
        return error('You are signed out.', 401, 'no_session')

    with c.db.session() as s:
        result = c.rotate(s, raw)
        payload = c.auth_payload(result.user, result.family_id) if result.ok else None

    if not result.ok:
        code = 'session_revoked' if result.reason in ('revoked', 'reuse', 'inactive') else 'session_expired'
        resp = error('Your session has ended. Sign in again.', 401, code)
        c.clear_refresh_cookie(resp)
        return resp
    resp = jsonify(payload)
    if result.new_token:
        c.set_refresh_cookie(resp, result.new_token, result.persistent)
    return resp


@bp.post('/logout')
@public
def logout():
    c = ctx()
    if not _csrf_ok():
        return error('Missing client header.', 403, 'csrf')
    raw = request.cookies.get(REFRESH_COOKIE)
    with c.db.session() as s:
        row = c.family_for_token(s, raw) if raw else None
        if row is not None:
            c.revoke_family(s, row.family_id)
    resp = jsonify({'ok': True})
    c.clear_refresh_cookie(resp)
    return resp


@bp.post('/logout-all')
def logout_all():
    c = ctx()
    with c.db.session() as s:
        c.revoke_all(s, current_user().id)
    resp = jsonify({'ok': True})
    c.clear_refresh_cookie(resp)
    return resp


@bp.post('/forgot')
@public
@rate_limit('forgot', 5, 900)
def forgot_password():
    c = ctx()
    email = normalise_email(json_body().get('email'))
    if not valid_email(email):
        return error('Enter a valid email address.', 400, 'invalid_email', field='email')

    # Links are only built from APP_URL when email is on, so a forged Host header
    # cannot send someone a reset link that points at another site.
    base = c.cfg.app_url or ('' if c.cfg.email_enabled else request.host_url.rstrip('/'))
    link = None
    with c.db.session() as s:
        user = s.scalar(select(User).where(User.email == email))
        if user is not None and user.is_active and base:
            s.execute(update(PasswordReset)
                      .where(PasswordReset.user_id == user.id, PasswordReset.used_at.is_(None))
                      .values(used_at=utcnow()))
            raw = new_opaque_token()
            s.add(PasswordReset(user_id=user.id, token_hash=token_digest(raw),
                                expires_at=utcnow() + RESET_TTL))
            link = f'{base}/reset-password?token={raw}'
        elif user is not None and not base:
            print('[auth] APP_URL is not set, so no password reset email was sent.')

    if link:
        send_mail(c.cfg, email, 'Reset your AquaCount password',
                  'Someone asked to reset the password for your AquaCount account.\n\n'
                  f'Open this link within 30 minutes to choose a new password:\n{link}\n\n'
                  'If this was not you, ignore this email. Your password has not changed.')
    return jsonify({
        'ok': True,
        'delivery': 'email' if c.cfg.email_enabled else 'console',
        'message': 'If an account exists for that email, a reset link is on its way.',
    }), 202


@bp.post('/reset')
@public
@rate_limit('reset', 10, 900)
def reset_password():
    c = ctx()
    data = json_body()
    raw = str(data.get('token') or '')
    password = data.get('password') or ''
    invalid = error('This reset link is invalid or has expired. Request a new one.', 400, 'invalid_token')
    if not raw:
        return invalid
    with c.db.session() as s:
        row = s.scalar(select(PasswordReset).where(PasswordReset.token_hash == token_digest(raw)))
        if row is None or row.used_at is not None or row.expires_at <= utcnow():
            return invalid
        user = s.get(User, row.user_id)
        if user is None or not user.is_active:
            return invalid
        problem = password_problem(password, user.email)
        if problem:
            return error(problem, 400, 'weak_password', field='password')
        user.password_hash = hash_password(password)
        user.password_changed_at = utcnow()
        row.used_at = utcnow()
        c.revoke_all(s, user.id)  # sign out everywhere: whoever knew the old password is out
    return jsonify({'ok': True, 'message': 'Password updated. Sign in with your new password.'})


@bp.post('/google/link')
@rate_limit('google-link', 10, 300, by='user')
def google_link():
    c = ctx()
    if not c.cfg.google_enabled:
        return error('Google sign-in is not set up on this server.', 400, 'google_disabled')
    try:
        claims = c.google.verify(str(json_body().get('credential') or ''))
    except GoogleVerificationError as e:
        return error(str(e), 401, 'google_invalid')
    with c.db.session() as s:
        other = s.scalar(select(User).where(User.google_sub == str(claims['sub'])))
        user = s.get(User, current_user().id)
        if other is not None and other.id != user.id:
            return error('That Google account is already connected to another AquaCount account.',
                         409, 'google_in_use')
        user.google_sub = str(claims['sub'])
        user.google_email = normalise_email(claims.get('email'))
        if claims.get('picture') and not user.avatar_url:
            user.avatar_url = str(claims['picture'])[:512]
        return jsonify({'user': user.to_dict()})


@bp.post('/google/unlink')
def google_unlink():
    c = ctx()
    with c.db.session() as s:
        user = s.get(User, current_user().id)
        if not user.password_hash:
            return error('Set a password first, so you can still sign in without Google.',
                         400, 'password_required')
        user.google_sub = None
        user.google_email = None
        return jsonify({'user': user.to_dict()})
