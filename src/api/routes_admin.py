"""/api/admin: user management and a read-only view of the station's counting setup."""

from __future__ import annotations

from flask import Blueprint, jsonify
from sqlalchemy import func, select

from api.config import APP_VERSION
from api.db import RunRecord, User, iso
from api.http import ctx, current_user, error, json_body, require_role

bp = Blueprint('admin', __name__, url_prefix='/api/admin')


@bp.get('/users')
@require_role('admin')
def list_users():
    with ctx().db.session() as s:
        run_counts = dict(s.execute(select(RunRecord.user_id, func.count(RunRecord.id))
                                    .group_by(RunRecord.user_id)).all())
        users = s.scalars(select(User).order_by(User.created_at)).all()
    return jsonify({'users': [{
        'id': u.public_id,
        'email': u.email,
        'name': u.name,
        'avatar_url': u.avatar_url,
        'role': u.role,
        'is_active': u.is_active,
        'google_connected': bool(u.google_sub),
        'has_password': bool(u.password_hash),
        'runs': int(run_counts.get(u.id, 0)),
        'created_at': iso(u.created_at),
        'last_login_at': iso(u.last_login_at),
        'is_you': u.id == current_user().id,
    } for u in users]})


@bp.patch('/users/<public_id>')
@require_role('admin')
def update_user(public_id: str):
    c = ctx()
    data = json_body()
    role = data.get('role')
    active = data.get('is_active')
    if role is not None and role not in ('admin', 'operator'):
        return error('Role must be admin or operator.', 400)
    if active is not None and not isinstance(active, bool):
        return error('is_active must be true or false.', 400)

    with c.db.session() as s:
        user = s.scalar(select(User).where(User.public_id == public_id))
        if user is None:
            return error('User not found.', 404)
        losing_admin = user.role == 'admin' and user.is_active and (role == 'operator' or active is False)
        if losing_admin:
            admins = s.scalar(select(func.count(User.id))
                              .where(User.role == 'admin', User.is_active.is_(True)))
            if admins <= 1:
                return error('The station needs at least one active administrator.', 400, 'last_admin')
        if role is not None:
            user.role = role
        if active is not None:
            user.is_active = active
            if not active:
                c.revoke_all(s, user.id)
        return jsonify({'user': {'id': user.public_id, 'role': user.role, 'is_active': user.is_active}})


@bp.get('/station')
@require_role('admin')
def station():
    c = ctx()
    server = c.server
    counter = getattr(server, 'counter', None)
    settings = {}
    correction = {}
    if counter is not None:
        try:
            settings = counter._run_settings()
        except Exception:
            settings = {}
        counting = (getattr(counter, 'config', {}) or {}).get('counting', {})
        correction = {'factor': counting.get('count_correction_factor', 1.0),
                      'note': counting.get('count_correction_note', '')}
    runs_dir = getattr(server, 'runs_dir', None)
    with c.db.session() as s:
        users = s.scalar(select(func.count(User.id))) or 0
        runs = s.scalar(select(func.count(RunRecord.id))) or 0
    return jsonify({
        'version': APP_VERSION,
        'model_loaded': counter is not None,
        'settings': settings,
        'calibration': correction,
        'is_processing': bool(getattr(server, 'is_processing', False)),
        'runs_dir': str(runs_dir) if runs_dir else None,
        'database': c.db.backend,
        'users': users,
        'runs_recorded': runs,
        'features': {
            'google_sign_in': c.cfg.google_enabled,
            'email': c.cfg.email_enabled,
            'open_signup': c.cfg.allow_signup,
        },
    })
