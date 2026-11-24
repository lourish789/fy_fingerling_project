import { useState } from 'react'
import { Link } from 'react-router-dom'
import { CircleAlert, Cpu, Scale, TriangleAlert, Users } from 'lucide-react'
import { useApi } from '../hooks/useApi'
import { usePageMeta } from '../components/layout/pageMeta'
import { Avatar, Badge, Callout, Card, ErrorState, Skeleton, SkeletonList } from '../components/ui/primitives'
import { useToast } from '../components/ui/feedback'
import { api, errorMessage } from '../lib/api'
import { formatNumber, formatRelative } from '../lib/format'
import type { AdminUser, StationConfig } from '../lib/types'

const SETTING_ROWS: [string, string][] = [
  ['model_file', 'Model file'],
  ['model_sha256_12', 'Model fingerprint'],
  ['confidence_threshold', 'Confidence threshold'],
  ['nms_iou_threshold', 'Overlap (NMS) threshold'],
  ['counting_mode', 'Counting mode'],
  ['count_direction', 'Counted direction'],
  ['counting_line_orientation', 'Counting line'],
  ['counting_line_position', 'Line position'],
  ['min_hits', 'Detections before counting'],
  ['max_distance_px', 'Max track jump (px)'],
  ['roi', 'Channel region (ROI)'],
]

function StationCard() {
  const { data, loading, error, reload } = useApi<StationConfig>('/api/admin/station')
  if (loading) return <div className="card stack"><Skeleton width="40%" height={18} /><Skeleton height={160} /></div>
  if (error || !data) return <Card><ErrorState icon={<CircleAlert />} message={error?.message} onRetry={reload} /></Card>
  const factor = Number(data.calibration.factor ?? 1)
  return (
    <>
      <Card title="Counting station" icon={<Cpu aria-hidden />} action={data.is_processing ? <Badge tone="live">Counting</Badge> : <Badge tone="success">Idle</Badge>}>
        <div className="stack">
          <div className="mini-stats">
            <div><span className="muted xsmall">Version</span><span className="num">{data.version}</span></div>
            <div><span className="muted xsmall">Model</span><span>{data.model_loaded ? 'Loaded' : 'Not loaded'}</span></div>
            <div><span className="muted xsmall">Accounts</span><span className="num">{data.users}</span></div>
            <div><span className="muted xsmall">Runs recorded</span><span className="num">{formatNumber(data.runs_recorded)}</span></div>
          </div>
          <dl className="kv">
            {SETTING_ROWS.filter(([k]) => data.settings[k] !== undefined && data.settings[k] !== null).map(([k, label]) => (
              <Row key={k} label={label} value={data.settings[k]} mono={k.startsWith('model')} />
            ))}
            <dt>Database</dt><dd>{data.database === 'sqlite' ? 'SQLite (this computer)' : data.database}</dd>
            <dt>Run files</dt><dd className="mono">{data.runs_dir ?? '—'}</dd>
            <dt>Google sign-in</dt><dd>{data.features.google_sign_in ? 'On' : 'Off (set GOOGLE_CLIENT_ID)'}</dd>
            <dt>Password-reset email</dt><dd>{data.features.email ? 'On' : 'Off: links print in the server window'}</dd>
            <dt>Open sign-up</dt><dd>{data.features.open_signup ? 'Anyone can create an account' : 'Off (ALLOW_SIGNUP=0)'}</dd>
          </dl>
          <p className="xsmall muted">Detection and counting settings come from <span className="mono">config/config.yaml</span>, the validated configuration. Change them there, then restart the server.</p>
        </div>
      </Card>
      <Card title="Calibration" icon={<Scale aria-hidden />}>
        {factor === 1 ? (
          <Callout tone="warning" icon={<TriangleAlert />}>
            <strong>Not calibrated yet.</strong> Reports show raw machine counts only. Hand-count 5 batches and run <span className="mono">scripts/calibrate.py</span> to get a correction factor.
          </Callout>
        ) : (
          <p>Correction factor <strong className="num">×{factor.toFixed(3)}</strong>. {data.calibration.note}</p>
        )}
      </Card>
    </>
  )
}

function Row({ label, value, mono }: { label: string; value: unknown; mono?: boolean }) {
  return (<><dt>{label}</dt><dd className={mono ? 'mono' : undefined}>{Array.isArray(value) ? value.join(', ') : String(value)}</dd></>)
}

function UsersCard() {
  const toast = useToast()
  const { data, loading, error, reload, setData } = useApi<{ users: AdminUser[] }>('/api/admin/users')
  const [busy, setBusy] = useState<string | null>(null)

  const update = async (u: AdminUser, patch: Partial<Pick<AdminUser, 'role' | 'is_active'>>) => {
    setBusy(u.id)
    try {
      const r = await api<{ user: Pick<AdminUser, 'id' | 'role' | 'is_active'> }>(`/api/admin/users/${encodeURIComponent(u.id)}`, { method: 'PATCH', json: patch })
      setData((d) => d && { users: d.users.map((x) => (x.id === u.id ? { ...x, ...r.user } : x)) })
      toast.show({ tone: 'success', message: `${u.name || u.email} updated.` })
    } catch (err) { toast.show({ tone: 'error', message: errorMessage(err) }) } finally { setBusy(null) }
  }

  return (
    <Card flush title={`People${data ? ` (${data.users.length})` : ''}`} icon={<Users aria-hidden />}>
      {loading ? <SkeletonList rows={3} /> : error ? <ErrorState icon={<CircleAlert />} message={error.message} onRetry={reload} /> : (
        <div className="list">
          {data?.users.map((u) => (
            <div key={u.id} className="list-item user-row" style={{ opacity: u.is_active ? 1 : 0.6 }}>
              <Avatar name={u.name} email={u.email} src={u.avatar_url} />
              <div className="grow" style={{ minWidth: 0 }}>
                <div className="row" style={{ gap: 6 }}>
                  <span className="truncate" style={{ fontWeight: 600 }}>{u.name || u.email}</span>
                  {u.is_you && <Badge tone="accent">You</Badge>}
                  {!u.is_active && <Badge tone="danger">Deactivated</Badge>}
                </div>
                <div className="xsmall muted truncate">
                  {u.email} · {formatNumber(u.runs)} runs · {u.last_login_at ? `active ${formatRelative(u.last_login_at)}` : 'never signed in'}
                  {u.google_connected ? ' · Google' : ''}
                </div>
              </div>
              <div className="user-actions">
                <select className="input select-sm" aria-label={`Role for ${u.name || u.email}`} value={u.role} disabled={busy === u.id}
                  onChange={(e) => update(u, { role: e.target.value as AdminUser['role'] })}>
                  <option value="operator">Operator</option>
                  <option value="admin">Admin</option>
                </select>
                {!u.is_you && (
                  <button className="btn btn-sm btn-ghost" disabled={busy === u.id} onClick={() => update(u, { is_active: !u.is_active })}>
                    {u.is_active ? 'Deactivate' : 'Reactivate'}
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
      <p className="xsmall muted" style={{ padding: '12px 16px' }}>Deactivating someone signs them out everywhere. Their runs stay in history. Admins can see every run in <Link to="/history">History</Link> and <Link to="/insights">Insights</Link>.</p>
    </Card>
  )
}

export function AdminPage() {
  usePageMeta({ title: 'Admin', subtitle: 'Station & people' })
  return (
    <div className="page">
      <div className="grid grid-lg-main">
        <div className="stack"><UsersCard /></div>
        <div className="stack"><StationCard /></div>
      </div>
    </div>
  )
}
