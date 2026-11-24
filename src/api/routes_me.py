"""/api/me: the signed-in user's profile, preferences, password and sessions."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from flask import Blueprint, g, jsonify
from sqlalchemy import func, select

from api.db import RefreshToken, RunRecord, User, iso, utcnow
from api.http import ctx, current_user, error, json_body, rate_limit
from api.security import hash_password, password_problem, verify_password

bp = Blueprint('me', __name__, url_prefix='/api/me')

CLASS_KEYS = ('fingerling', 'post_fingerling', 'juvenile')

# key -> validator returning (ok, cleaned value)
PREFERENCES = {
    'theme': ('enum', ('system', 'light', 'dark')),
    'hatchery_name': ('str', 80),
    'role_title': ('str', 60),
    'setup_type': ('enum', ('channel', 'webcam', 'ip_camera', 'uploads')),
    'size_focus': ('list', CLASS_KEYS),
    'daily_target': ('int', (0, 10_000_000)),
    'default_source': ('enum', ('camera', 'upload', 'batch', 'url')),
    'camera_index': ('int', (0, 9)),
    'stream_url': ('str', 500),
    'compact_numbers': ('bool', None),
    'haptics': ('bool', None),
}


def _clean_pref(key: str, value: Any) -> Tuple[bool, Any]:
    kind, rule = PREFERENCES[key]
    if kind == 'enum':
        return (value in rule), value
    if kind == 'str':
        if value is None:
            return True, ''
        return isinstance(value, str), (value.strip()[:rule] if isinstance(value, str) else None)
    if kind == 'bool':
        return isinstance(value, bool), value
    if kind == 'int':
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False, None
        lo, hi = rule
        return lo <= int(value) <= hi, int(value)
    if kind == 'list':
        if not isinstance(value, list) or any(v not in rule for v in value):
            return False, None
        return True, [v for v in rule if v in value]  # stable order, no duplicates
    return False, None


def clean_preferences(data: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    cleaned: Dict[str, Any] = {}
    for key, value in data.items():
        if key not in PREFERENCES:
            return None, f'Unknown preference: {key}'
        ok, val = _clean_pref(key, value)
        if not ok:
            return None, f'Invalid value for {key}'
        cleaned[key] = val
    return cleaned, None


@bp.get('')
def me():
    with ctx().db.session() as s:
        user = s.get(User, current_user().id)
        stats = s.execute(select(func.count(RunRecord.id), func.coalesce(func.sum(RunRecord.total), 0))
                          .where(RunRecord.user_id == user.id)).one()
        return jsonify({'user': user.to_dict(),
                        'stats': {'runs': int(stats[0]), 'fish_counted': int(stats[1])}})


@bp.patch('')
def update_me():
    data = json_body()
    with ctx().db.session() as s:
        user = s.get(User, current_user().id)
        if 'name' in data:
            name = str(data.get('name') or '').strip()[:120]
            if not name:
                return error('Enter your name.', 400, 'invalid_name', field='name')
            user.name = name
        return jsonify({'user': user.to_dict()})


@bp.patch('/preferences')
def update_preferences():
    cleaned, problem = clean_preferences(json_body())
    if problem:
        return error(problem, 400, 'invalid_preferences')
    with ctx().db.session() as s:
        user = s.get(User, current_user().id)
        user.preferences = {**user.preferences, **cleaned}
        return jsonify({'user': user.to_dict()})


@bp.post('/onboarding')
def complete_onboarding():
    data = json_body()
    name = data.pop('name', None)
    cleaned, problem = clean_preferences(data)
    if problem:
        return error(problem, 400, 'invalid_preferences')
    with ctx().db.session() as s:
        user = s.get(User, current_user().id)
        if isinstance(name, str) and name.strip():
            user.name = name.strip()[:120]
        user.preferences = {**user.preferences, **cleaned}
        user.onboarded = True
        return jsonify({'user': user.to_dict()})


@bp.post('/password')
@rate_limit('password-change', 10, 900, by='user')
def change_password():
    c = ctx()
    data = json_body()
    new_password = data.get('new_password') or ''
    with c.db.session() as s:
        user = s.get(User, current_user().id)
        if user.password_hash and not verify_password(user.password_hash, data.get('current_password') or ''):
            return error('Your current password is incorrect.', 400, 'invalid_credentials',
                         field='current_password')
        problem = password_problem(new_password, user.email)
        if problem:
            return error(problem, 400, 'weak_password', field='new_password')
        had_password = bool(user.password_hash)
        user.password_hash = hash_password(new_password)
        user.password_changed_at = utcnow()
        c.revoke_all(s, user.id, except_family=g.claims.get('sid'))
        return jsonify({'user': user.to_dict(),
                        'message': 'Password changed. Other devices have been signed out.'
                        if had_password else 'Password set. You can now sign in with email too.'})


@bp.get('/sessions')
def list_sessions():
    c = ctx()
    current_sid = g.claims.get('sid')
    now = utcnow()
    with c.db.session() as s:
        rows = s.scalars(select(RefreshToken).where(
            RefreshToken.user_id == current_user().id,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.rotated_at.is_(None),
            RefreshToken.expires_at > now,
        ).order_by(RefreshToken.created_at.desc())).all()
    sessions = [{
        'id': r.family_id,
        'user_agent': r.user_agent,
        'ip': r.ip,
        'signed_in_at': iso(r.family_created_at),
        'last_active_at': iso(r.created_at),
        'expires_at': iso(r.expires_at),
        'current': r.family_id == current_sid,
    } for r in rows]
    sessions.sort(key=lambda x: x['last_active_at'] or '', reverse=True)
    sessions.sort(key=lambda x: not x['current'])  # stable: this device first, then most recent
    return jsonify({'sessions': sessions})


@bp.delete('/sessions/<family_id>')
def revoke_session(family_id: str):
    c = ctx()
    with c.db.session() as s:
        owned = s.scalar(select(RefreshToken.id).where(RefreshToken.family_id == family_id,
                                                       RefreshToken.user_id == current_user().id).limit(1))
        if owned is None:
            return error('Session not found.', 404)
        c.revoke_family(s, family_id)
    return jsonify({'ok': True, 'current': family_id == g.claims.get('sid')})


@bp.delete('')
@rate_limit('account-delete', 5, 900, by='user')
def delete_account():
    c = ctx()
    data = json_body()
    if data.get('confirm') != 'DELETE':
        return error('Type DELETE to confirm.', 400, 'confirmation_required', field='confirm')
    with c.db.session() as s:
        user = s.get(User, current_user().id)
        if user.password_hash and not verify_password(user.password_hash, data.get('password') or ''):
            return error('Your password is incorrect.', 400, 'invalid_credentials', field='password')
        if user.role == 'admin':
            admins = s.scalar(select(func.count(User.id)).where(User.role == 'admin', User.is_active.is_(True)))
            if admins <= 1 and s.scalar(select(func.count(User.id))) > 1:
                return error('Make another user an administrator before deleting this account.',
                             400, 'last_admin')
        s.delete(user)  # runs stay on record, unassigned; sessions and reset links cascade
    resp = jsonify({'ok': True})
    c.clear_refresh_cookie(resp)
    return resp
