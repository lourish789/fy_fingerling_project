"""
/api/runs, /api/insights, /api/stream-token: per-user count history.

Each run's audit trail stays on disk (output/runs/<run_id>/). The `runs` table
records who started it and its headline numbers, so history and insights are
fast and scoped to the signed-in user. Administrators can see every run,
including ones recorded before accounts existed.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from flask import Blueprint, jsonify, request, send_from_directory
from sqlalchemy import func, or_, select

from api.db import RunRecord, User, utcnow
from api.http import ctx, current_user, error

bp = Blueprint('runs', __name__, url_prefix='/api')

RUN_ID_PATTERN = re.compile(r'^[A-Za-z0-9_-]{1,120}$')
CLASS_KEYS = ('fingerling', 'post_fingerling', 'juvenile', 'unknown')
FILE_LABELS = {
    'report.html': 'Printable report',
    'events.csv': 'Fish log (CSV)',
    'summary.json': 'Summary (JSON)',
    'batch_summary.csv': 'Batch summary (CSV)',
    'annotated.jpg': 'Annotated image',
}
CROP_NAME = re.compile(r'^(\d+)_([a-z_]+)\.jpg$')


# ── Persistence (called from the counting thread) ───────────────────────────
def _local_iso_to_utc(value: Any) -> Optional[datetime]:
    """Run summaries hold local wall-clock times; store them as naive UTC."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def persist_run(c, summary: Dict[str, Any], kind: str, owner_id: Optional[int]) -> None:
    run_id = str(summary.get('run_id') or '')
    if not RUN_ID_PATTERN.match(run_id):
        return
    counts = {k: int((summary.get('counts') or {}).get(k, 0) or 0) for k in ('total', *CLASS_KEYS)}
    with c.db.session() as s:
        rec = s.scalar(select(RunRecord).where(RunRecord.run_id == run_id))
        if rec is None:
            rec = RunRecord(run_id=run_id)
            s.add(rec)
        if owner_id is not None and rec.user_id is None:
            rec.user_id = owner_id
        rec.kind = kind
        rec.source = str(summary.get('source') or '')[:255]
        rec.status = str(summary.get('status') or 'completed')[:24]
        rec.total = counts['total']
        rec.counts_json = json.dumps(counts)
        rec.corrected_total = summary.get('corrected_total')
        rec.correction_factor = summary.get('correction_factor')
        rec.warning = str(summary.get('warning') or '')
        rec.frames_processed = int(summary.get('frames_processed') or 0)
        rec.processing_seconds = float(summary.get('processing_seconds') or 0.0)
        rec.started_at = _local_iso_to_utc(summary.get('started_at'))
        rec.ended_at = _local_iso_to_utc(summary.get('ended_at'))


def _legacy_batch_summary(run_dir: Path) -> Optional[Dict[str, Any]]:
    """Batches recorded before summary.json existed only have batch_summary.csv."""
    path = run_dir / 'batch_summary.csv'
    if not path.exists():
        return None
    totals = Counter()
    with open(path, encoding='utf-8', newline='') as f:
        for row in csv.DictReader(f):
            for k in ('total', *CLASS_KEYS):
                try:
                    totals[k] += int(row.get(k) or 0)
                except ValueError:
                    pass
    started = None
    m = re.match(r'^(\d{8})_(\d{6})', run_dir.name)
    if m:
        started = datetime.strptime(m.group(1) + m.group(2), '%Y%m%d%H%M%S').isoformat()
    return {'run_id': run_dir.name, 'kind': 'batch', 'status': 'completed', 'source': 'batch images',
            'counts': dict(totals), 'started_at': started, 'ended_at': started}


def sync_disk_runs(c) -> int:
    """Register run folders that have no database row yet (e.g. recorded before accounts existed)."""
    runs_dir: Optional[Path] = getattr(c.server, 'runs_dir', None)
    if runs_dir is None or not runs_dir.is_dir():
        return 0
    with c.db.session() as s:
        known = set(s.scalars(select(RunRecord.run_id)).all())
    added = 0
    for d in runs_dir.iterdir():
        if not d.is_dir() or d.name in known or not RUN_ID_PATTERN.match(d.name):
            continue
        summary = None
        if (d / 'summary.json').exists():
            try:
                summary = json.loads((d / 'summary.json').read_text(encoding='utf-8'))
            except (OSError, ValueError):
                summary = None
        if summary is None:
            summary = _legacy_batch_summary(d)
        if not summary:
            continue  # still running, or not a run
        summary.setdefault('run_id', d.name)
        kind = summary.get('kind') or ('batch' if (d / 'batch_summary.csv').exists() else 'video')
        persist_run(c, summary, kind, None)
        added += 1
    return added


# ── Access control ───────────────────────────────────────────────────────────
def _scope_all() -> bool:
    return request.args.get('scope') == 'all' and current_user().role == 'admin'


def _load_run(run_id: str):
    """(record, owner) the current user may see, else (None, None). Unknown and forbidden look alike."""
    if not RUN_ID_PATTERN.match(run_id):
        return None, None
    c = ctx()
    user = current_user()
    with c.db.session() as s:
        row = s.execute(select(RunRecord, User).outerjoin(User, RunRecord.user_id == User.id)
                        .where(RunRecord.run_id == run_id)).first()
    if row is None and user.role == 'admin' and sync_disk_runs(c):
        with c.db.session() as s:
            row = s.execute(select(RunRecord, User).outerjoin(User, RunRecord.user_id == User.id)
                            .where(RunRecord.run_id == run_id)).first()
    if row is None:
        return None, None
    rec, owner = row
    if user.role != 'admin' and rec.user_id != user.id:
        return None, None
    return rec, owner


def _run_dir(run_id: str) -> Optional[Path]:
    runs_dir = getattr(ctx().server, 'runs_dir', None)
    if runs_dir is None:
        return None
    d = Path(runs_dir) / run_id
    return d if d.is_dir() else None


# ── Endpoints ────────────────────────────────────────────────────────────────
@bp.get('/runs')
def list_runs():
    c = ctx()
    user = current_user()
    all_scope = _scope_all()
    if all_scope:
        sync_disk_runs(c)
    try:
        limit = max(1, min(int(request.args.get('limit', 30)), 100))
        offset = max(0, int(request.args.get('offset', 0)))
    except ValueError:
        return error('limit and offset must be whole numbers.', 400)

    stmt = select(RunRecord, User).outerjoin(User, RunRecord.user_id == User.id)
    count = select(func.count(RunRecord.id))
    filters = []
    if not all_scope:
        filters.append(RunRecord.user_id == user.id)
    if request.args.get('status'):
        filters.append(RunRecord.status == request.args['status'])
    if request.args.get('kind'):
        filters.append(RunRecord.kind == request.args['kind'])
    q = (request.args.get('q') or '').strip()
    if q:
        like = f'%{q[:80]}%'
        filters.append(or_(RunRecord.run_id.ilike(like), RunRecord.source.ilike(like)))
    for f in filters:
        stmt = stmt.where(f)
        count = count.where(f)
    order = func.coalesce(RunRecord.started_at, RunRecord.created_at).desc()

    with c.db.session() as s:
        total = s.scalar(count) or 0
        rows = s.execute(stmt.order_by(order, RunRecord.id.desc()).offset(offset).limit(limit)).all()
    runs = [rec.to_dict(owner) for rec, owner in rows]
    return jsonify({'runs': runs, 'total': total, 'limit': limit, 'offset': offset,
                    'has_more': offset + len(runs) < total, 'scope': 'all' if all_scope else 'mine'})


@bp.get('/runs/<run_id>')
def run_detail(run_id: str):
    c = ctx()
    rec, owner = _load_run(run_id)
    if rec is None:
        return error('Run not found.', 404)
    run_dir = _run_dir(run_id)
    summary, files, crops, crops_total, images = None, [], [], 0, []
    if run_dir is not None:
        try:
            summary = json.loads((run_dir / 'summary.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            summary = None
        for name, label in FILE_LABELS.items():
            p = run_dir / name
            if p.is_file():
                files.append({'name': name, 'label': label, 'bytes': p.stat().st_size})
        crops_dir = run_dir / 'crops'
        if crops_dir.is_dir():
            names = sorted(p.name for p in crops_dir.glob('*.jpg'))
            crops_total = len(names)
            for name in names[-120:]:  # the most recent fish are the most useful to spot-check
                m = CROP_NAME.match(name)
                crops.append({'path': f'crops/{name}', 'seq': int(m.group(1)) if m else None,
                              'class': m.group(2) if m else 'unknown'})
        images_dir = run_dir / 'images'
        if images_dir.is_dir():
            images = [f'images/{p.name}' for p in sorted(images_dir.glob('*.jpg'))[:200]]

    if summary and isinstance(summary.get('results'), list):
        summary['results'] = summary['results'][:200]
    user = current_user()
    return jsonify({
        'run': rec.to_dict(owner),
        'summary': summary,
        'files_available': run_dir is not None,
        'files': files,
        'crops': crops,
        'crops_total': crops_total,
        'images': images,
        'media_token': c.tokens.issue_media(user.public_id, f'run:{run_id}'),
        'media_expires_in': int(c.tokens.media_ttl.total_seconds()),
    })


@bp.get('/runs/<run_id>/<path:filename>')
def run_file(run_id: str, filename: str):
    rec, _ = _load_run(run_id)
    if rec is None:
        return error('Run not found.', 404)
    run_dir = _run_dir(run_id)
    if run_dir is None:
        return error('The files for this run are no longer on this server.', 404, 'files_missing')
    resp = send_from_directory(run_dir, filename, as_attachment=request.args.get('download') == '1')
    # Reports are generated HTML: render them inert, with no scripts or outside requests.
    resp.headers['Content-Security-Policy'] = ("sandbox; default-src 'none'; style-src 'unsafe-inline'; "
                                               "img-src 'self' data:")
    resp.headers['Cache-Control'] = 'private, max-age=300'
    return resp


@bp.get('/stream-token')
def stream_token():
    c = ctx()
    return jsonify({'token': c.tokens.issue_media(current_user().public_id, 'stream'),
                    'expires_in': int(c.tokens.media_ttl.total_seconds())})


@bp.get('/insights')
def insights():
    c = ctx()
    user = current_user()
    all_scope = _scope_all()
    try:
        days = max(1, min(int(request.args.get('days', 14)), 366))
        tz_offset = max(-840, min(int(request.args.get('tz_offset', 0)), 840))  # JS getTimezoneOffset()
    except ValueError:
        return error('days and tz_offset must be whole numbers.', 400)
    shift = timedelta(minutes=-tz_offset)

    when = func.coalesce(RunRecord.started_at, RunRecord.created_at)
    base = select(RunRecord)
    if not all_scope:
        base = base.where(RunRecord.user_id == user.id)
    today_local = (utcnow() + shift).date()
    first_day = today_local - timedelta(days=days - 1)
    since_utc = datetime.combine(first_day, datetime.min.time()) - shift

    with c.db.session() as s:
        rows = s.scalars(base.where(when >= since_utc)).all()
        lifetime = s.execute(
            select(func.count(RunRecord.id), func.coalesce(func.sum(RunRecord.total), 0))
            .where(*([] if all_scope else [RunRecord.user_id == user.id]))
        ).one()

    per_day = {first_day + timedelta(days=i): {'fish': 0, 'runs': 0} for i in range(days)}
    classes: Counter = Counter()
    statuses: Counter = Counter()
    kinds: Counter = Counter()
    fps_samples = []
    hourly = defaultdict(int)
    for r in rows:
        t = (r.started_at or r.created_at) + shift
        bucket = per_day.get(t.date())
        if bucket is not None:
            bucket['fish'] += r.total
            bucket['runs'] += 1
        hourly[t.hour] += r.total
        statuses[r.status] += 1
        kinds[r.kind] += 1
        for k in CLASS_KEYS:
            classes[k] += r.counts.get(k, 0)
        if r.kind in ('video', 'camera', 'url') and r.processing_seconds > 0 and r.frames_processed:
            fps_samples.append(r.frames_processed / r.processing_seconds)

    fish = sum(r.total for r in rows)
    series = [{'date': d.isoformat(), **v} for d, v in sorted(per_day.items())]
    best = max(series, key=lambda x: x['fish']) if series else None
    today = per_day.get(today_local, {'fish': 0, 'runs': 0})
    return jsonify({
        'scope': 'all' if all_scope else 'mine',
        'days': days,
        'today': today,
        'period': {
            'fish': fish,
            'runs': len(rows),
            'avg_fish_per_run': round(fish / len(rows), 1) if rows else 0,
            'best_day': best if best and best['fish'] > 0 else None,
            'avg_processing_fps': round(sum(fps_samples) / len(fps_samples), 2) if fps_samples else None,
            'completed_share': round(statuses.get('completed', 0) / len(rows), 3) if rows else None,
        },
        'lifetime': {'runs': int(lifetime[0]), 'fish': int(lifetime[1])},
        'series': series,
        'classes': {k: classes.get(k, 0) for k in CLASS_KEYS},
        'statuses': dict(statuses),
        'kinds': dict(kinds),
        'busiest_hour': max(hourly, key=hourly.get) if hourly else None,
    })
