import { useState, type FormEvent } from 'react'
import { CircleAlert, KeyRound, Laptop, LogOut, Pencil, ShieldCheck, Smartphone, Tablet, Trash2 } from 'lucide-react'
import { useAuth, useUser } from '../auth/AuthProvider'
import { useApi } from '../hooks/useApi'
import { usePageMeta } from '../components/layout/pageMeta'
import { Avatar, Badge, Button, Card, ErrorState, PasswordField, SkeletonList, TextField } from '../components/ui/primitives'
import { ConfirmDialog, Dialog, useToast } from '../components/ui/feedback'
import { GoogleButton, GoogleMark } from '../components/GoogleButton'
import { api, ApiError, errorMessage } from '../lib/api'
import { describeDevice, formatDate, formatNumber, formatRelative } from '../lib/format'
import type { SessionInfo, User } from '../lib/types'

function AccountCard({ user }: { user: User }) {
  const { setUser } = useAuth()
  const toast = useToast()
  const stats = useApi<{ stats: { runs: number; fish_counted: number } }>('/api/me')
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(user.name)
  const [busy, setBusy] = useState(false)

  const save = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      const r = await api<{ user: User }>('/api/me', { method: 'PATCH', json: { name } })
      setUser(r.user)
      setEditing(false)
      toast.show({ tone: 'success', message: 'Name updated.' })
    } catch (err) { toast.show({ tone: 'error', message: errorMessage(err) }) } finally { setBusy(false) }
  }

  return (
    <Card>
      <div className="profile-head">
        <Avatar name={user.name} email={user.email} src={user.avatar_url} size="xl" />
        <div className="grow" style={{ minWidth: 0 }}>
          {editing ? (
            <form className="stack-sm" onSubmit={save}>
              <TextField label="Name" value={name} onChange={(e) => setName(e.target.value)} autoFocus maxLength={120} />
              <div className="row"><Button type="submit" variant="primary" size="sm" loading={busy}>Save</Button>
                <Button size="sm" variant="ghost" onClick={() => { setEditing(false); setName(user.name) }}>Cancel</Button></div>
            </form>
          ) : (
            <>
              <div className="row" style={{ gap: 8 }}>
                <h2 className="truncate" style={{ fontSize: 'var(--text-xl)' }}>{user.name || 'Unnamed'}</h2>
                <button className="icon-btn" onClick={() => setEditing(true)} aria-label="Edit name"><Pencil /></button>
              </div>
              <div className="secondary truncate">{user.email}</div>
              <div className="row wrap" style={{ gap: 6, marginTop: 8 }}>
                <Badge tone="accent" icon={<ShieldCheck />}>{user.role === 'admin' ? 'Administrator' : 'Operator'}</Badge>
                {user.preferences.role_title && <Badge>{user.preferences.role_title}</Badge>}
              </div>
            </>
          )}
        </div>
      </div>
      <div className="mini-stats" style={{ marginTop: 16 }}>
        <div><span className="muted xsmall">Member since</span><span>{formatDate(user.created_at)}</span></div>
        <div><span className="muted xsmall">Runs</span><span className="num">{stats.data ? formatNumber(stats.data.stats.runs) : '—'}</span></div>
        <div><span className="muted xsmall">Fish counted</span><span className="num">{stats.data ? formatNumber(stats.data.stats.fish_counted, true) : '—'}</span></div>
        <div><span className="muted xsmall">Hatchery</span><span className="truncate">{user.preferences.hatchery_name || '—'}</span></div>
      </div>
    </Card>
  )
}

function ConnectedAccounts({ user }: { user: User }) {
  const { config, setUser } = useAuth()
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  const [confirm, setConfirm] = useState(false)

  const link = async (credential: string) => {
    setBusy(true)
    try {
      const r = await api<{ user: User }>('/api/auth/google/link', { base: 'auth', json: { credential } })
      setUser(r.user)
      toast.show({ tone: 'success', message: 'Google account connected. You can now sign in with Google.' })
    } catch (err) { toast.show({ tone: 'error', message: errorMessage(err) }) } finally { setBusy(false) }
  }
  const unlink = async () => {
    setBusy(true)
    try {
      const r = await api<{ user: User }>('/api/auth/google/unlink', { method: 'POST', base: 'auth' })
      setUser(r.user)
      setConfirm(false)
      toast.show({ tone: 'success', message: 'Google account disconnected.' })
    } catch (err) { toast.show({ tone: 'error', message: errorMessage(err) }) } finally { setBusy(false) }
  }

  return (
    <Card title="Connected accounts" sub="Sign in faster, without a password">
      <div className="connected-row">
        <span className="list-item-icon" style={{ background: '#fff' }}><GoogleMark /></span>
        <div className="grow" style={{ minWidth: 0 }}>
          <div style={{ fontWeight: 600 }}>Google</div>
          <div className="small muted truncate">{user.google_connected ? `Connected as ${user.google_email}` : config?.google_client_id ? 'Not connected' : 'Not available on this station'}</div>
        </div>
        {user.google_connected && <Button size="sm" variant="outline" onClick={() => setConfirm(true)} disabled={busy}>Disconnect</Button>}
      </div>
      {!user.google_connected && config?.google_client_id && (
        <div style={{ marginTop: 12 }}><GoogleButton clientId={config.google_client_id} onCredential={link} disabled={busy} /></div>
      )}
      <ConfirmDialog open={confirm} onClose={() => setConfirm(false)} onConfirm={unlink} busy={busy}
        title="Disconnect Google?" confirmLabel="Disconnect"
        message={user.has_password ? 'You will sign in with your email and password instead.' : 'Set a password first, so you can still sign in.'} />
    </Card>
  )
}

function PasswordCard({ user }: { user: User }) {
  const { setUser } = useAuth()
  const toast = useToast()
  const [open, setOpen] = useState(false)
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [errors, setErrors] = useState<{ current_password?: string; new_password?: string; form?: string }>({})
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (next.length < 8) { setErrors({ new_password: 'Use at least 8 characters.' }); return }
    setBusy(true)
    setErrors({})
    try {
      const r = await api<{ user: User; message: string }>('/api/me/password', { json: { current_password: current, new_password: next } })
      setUser(r.user)
      toast.show({ tone: 'success', message: r.message })
      setOpen(false); setCurrent(''); setNext('')
    } catch (err) {
      if (err instanceof ApiError && (err.field === 'current_password' || err.field === 'new_password')) setErrors({ [err.field]: err.message })
      else setErrors({ form: errorMessage(err) })
    } finally { setBusy(false) }
  }

  return (
    <Card title="Password" sub={user.has_password ? 'Changing it signs out your other devices.' : 'You sign in with Google. Add a password to sign in with email too.'}
      action={<Button size="sm" variant="outline" icon={<KeyRound />} onClick={() => setOpen(true)}>{user.has_password ? 'Change' : 'Set password'}</Button>}>
      <Dialog open={open} onClose={() => setOpen(false)} title={user.has_password ? 'Change password' : 'Set a password'}>
        <form className="stack" onSubmit={submit} noValidate>
          {errors.form && <div className="field-error" role="alert"><CircleAlert />{errors.form}</div>}
          {user.has_password && <PasswordField label="Current password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} error={errors.current_password} />}
          <PasswordField label="New password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} error={errors.new_password} hint="At least 8 characters." />
          <div className="row" style={{ justifyContent: 'flex-end' }}>
            <Button variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
            <Button type="submit" variant="primary" loading={busy}>Save password</Button>
          </div>
        </form>
      </Dialog>
    </Card>
  )
}

function SessionsCard() {
  const { logout, logoutEverywhere } = useAuth()
  const toast = useToast()
  const { data, loading, error, reload, setData } = useApi<{ sessions: SessionInfo[] }>('/api/me/sessions')
  const [busyId, setBusyId] = useState<string | null>(null)
  const [confirmAll, setConfirmAll] = useState(false)

  const revoke = async (s: SessionInfo) => {
    if (s.current) { await logout(); return }
    setBusyId(s.id)
    try {
      await api(`/api/me/sessions/${encodeURIComponent(s.id)}`, { method: 'DELETE' })
      setData((d) => d && { sessions: d.sessions.filter((x) => x.id !== s.id) })
      toast.show({ tone: 'success', message: 'That device has been signed out.' })
    } catch (err) { toast.show({ tone: 'error', message: errorMessage(err) }) } finally { setBusyId(null) }
  }

  const icon = (kind: string) => (kind === 'phone' ? <Smartphone aria-hidden /> : kind === 'tablet' ? <Tablet aria-hidden /> : <Laptop aria-hidden />)

  return (
    <Card flush title="Where you're signed in" action={<span style={{ paddingRight: 16 }}><Button size="sm" variant="ghost" icon={<LogOut />} onClick={() => setConfirmAll(true)}>Sign out everywhere</Button></span>}>
      {loading ? <SkeletonList rows={2} /> : error ? <ErrorState icon={<CircleAlert />} message={error.message} onRetry={reload} /> : (
        <div className="list">
          {data?.sessions.map((s) => {
            const dev = describeDevice(s.user_agent)
            return (
              <div key={s.id} className="list-item">
                <span className="list-item-icon">{icon(dev.kind)}</span>
                <div className="grow" style={{ minWidth: 0 }}>
                  <div className="row" style={{ gap: 8 }}><span className="truncate" style={{ fontWeight: 600 }}>{dev.label}</span>{s.current && <Badge tone="success">This device</Badge>}</div>
                  <div className="xsmall muted">Active {formatRelative(s.last_active_at)} · signed in {formatDate(s.signed_in_at)}{s.ip ? ` · ${s.ip}` : ''}</div>
                </div>
                <Button size="sm" variant="ghost" loading={busyId === s.id} onClick={() => revoke(s)}>Sign out</Button>
              </div>
            )
          })}
        </div>
      )}
      <ConfirmDialog open={confirmAll} onClose={() => setConfirmAll(false)} onConfirm={() => logoutEverywhere().catch((e) => toast.show({ tone: 'error', message: errorMessage(e) }))}
        title="Sign out everywhere?" confirmLabel="Sign out everywhere" danger
        message="Every device, including this one, will need to sign in again." />
    </Card>
  )
}

function DangerZone({ user }: { user: User }) {
  const { logout } = useAuth()
  const toast = useToast()
  const [open, setOpen] = useState(false)
  const [confirm, setConfirm] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api('/api/me', { method: 'DELETE', json: { confirm, password } })
      toast.show({ tone: 'success', message: 'Your account has been deleted.' })
      await logout()
    } catch (err) { setError(errorMessage(err)); setBusy(false) }
  }

  return (
    <Card title="Delete account" sub="Your past runs stay on the station's record, without your name.">
      <Button variant="danger-text" icon={<Trash2 />} onClick={() => setOpen(true)}>Delete my account</Button>
      <Dialog open={open} onClose={() => setOpen(false)} title="Delete your account?">
        <form className="stack" onSubmit={submit} noValidate>
          <p className="secondary small">This cannot be undone. Type <strong>DELETE</strong> to confirm.</p>
          {error && <div className="field-error" role="alert"><CircleAlert />{error}</div>}
          <TextField label="Confirmation" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoCapitalize="characters" autoComplete="off" />
          {user.has_password && <PasswordField label="Your password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />}
          <div className="row" style={{ justifyContent: 'flex-end' }}>
            <Button variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
            <Button type="submit" variant="danger" loading={busy} disabled={confirm !== 'DELETE'}>Delete account</Button>
          </div>
        </form>
      </Dialog>
    </Card>
  )
}

export function ProfilePage() {
  const user = useUser()
  usePageMeta({ title: 'Profile' })
  return (
    <div className="page page-narrow">
      <AccountCard user={user} />
      <section className="section" aria-label="Sign-in and security">
        <h2 className="section-title">Sign-in &amp; security</h2>
        <ConnectedAccounts user={user} />
        <PasswordCard user={user} />
        <SessionsCard />
      </section>
      <DangerZone user={user} />
    </div>
  )
}
