import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { ArrowLeft, CircleCheck, KeyRound, LockKeyhole, Mail, MonitorSmartphone, TriangleAlert } from 'lucide-react'
import { api, ApiError, errorMessage } from '../../lib/api'
import { useAuth } from '../../auth/AuthProvider'
import { BrandLockup } from '../../components/BrandMark'
import { Button, Callout, EmptyState, PasswordField, TextField } from '../../components/ui/primitives'
import { useCountdown } from './AuthLayout'

export function ForgotPasswordPage() {
  const { config } = useAuth()
  const [email, setEmail] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [sent, setSent] = useState<{ delivery: 'email' | 'console' } | null>(null)
  const [lockedUntil, setLockedUntil] = useState<number | null>(null)
  const wait = useCountdown(lockedUntil)

  useEffect(() => { document.title = 'Reset password · AquaCount' }, [])

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!/^\S+@\S+\.\S+$/.test(email.trim())) { setError('Enter the email address you signed up with.'); return }
    setBusy(true)
    setError(null)
    try {
      const r = await api<{ delivery: 'email' | 'console' }>('/api/auth/forgot', { base: 'auth', auth: false, json: { email: email.trim() } })
      setSent({ delivery: r.delivery })
    } catch (err) {
      if (err instanceof ApiError && err.isRateLimited && err.retryAfter) setLockedUntil(Date.now() + err.retryAfter * 1000)
      setError(errorMessage(err))
    } finally { setBusy(false) }
  }

  if (sent) {
    return (
      <div className="auth-card">
        <div className="auth-logo auth-logo-mobile"><BrandLockup /></div>
        {sent.delivery === 'email' ? (
          <EmptyState icon={<Mail />} title="Check your email"
            action={<Link className="btn btn-outline" to="/login"><ArrowLeft />Back to sign in</Link>}>
            If an account exists for {email.trim()}, a reset link is on its way. It works for 30 minutes.
          </EmptyState>
        ) : (
          <EmptyState icon={<MonitorSmartphone />} title="Ask your station administrator"
            action={<Link className="btn btn-outline" to="/login"><ArrowLeft />Back to sign in</Link>}>
            This station has no email set up. If {email.trim()} has an account, the reset link was printed in the
            AquaCount server window on the hatchery computer. It works for 30 minutes.
          </EmptyState>
        )}
      </div>
    )
  }

  return (
    <div className="auth-card">
      <div className="auth-logo auth-logo-mobile"><BrandLockup /></div>
      <div>
        <h1>Forgot your password?</h1>
        <p className="lead">Enter your email and we will send you a link to choose a new one.</p>
      </div>
      {config?.password_reset === 'console' && (
        <Callout tone="info" icon={<MonitorSmartphone />}>This station has no email set up, so the link appears on the hatchery computer instead.</Callout>
      )}
      <form className="stack" onSubmit={onSubmit} noValidate>
        <TextField label="Email" type="email" autoComplete="email" inputMode="email" autoCapitalize="off" autoFocus
          icon={<Mail className="input-icon" aria-hidden />} value={email} onChange={(e) => setEmail(e.target.value)} error={error} />
        <Button type="submit" variant="primary" size="lg" block loading={busy} disabled={wait > 0}>
          {wait > 0 ? `Try again in ${wait}s` : 'Send reset link'}
        </Button>
      </form>
      <p className="auth-foot"><Link to="/login">Back to sign in</Link></p>
    </div>
  )
}

export function ResetPasswordPage() {
  const [params] = useSearchParams()
  const token = params.get('token') || ''
  const navigate = useNavigate()
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [errors, setErrors] = useState<{ password?: string; confirm?: string; form?: string }>({})
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)

  useEffect(() => { document.title = 'Choose a new password · AquaCount' }, [])
  useEffect(() => { if (!done) return; const t = setTimeout(() => navigate('/login', { replace: true }), 4000); return () => clearTimeout(t) }, [done, navigate])

  if (!token) {
    return (
      <div className="auth-card">
        <EmptyState icon={<KeyRound />} title="This link is incomplete"
          action={<Link className="btn btn-primary" to="/forgot-password">Request a new link</Link>}>
          Open the reset link exactly as it was sent, or request a new one.
        </EmptyState>
      </div>
    )
  }

  if (done) {
    return (
      <div className="auth-card">
        <EmptyState icon={<CircleCheck />} title="Password updated"
          action={<Link className="btn btn-primary" to="/login" replace>Sign in</Link>}>
          You have been signed out on every device. Sign in with your new password.
        </EmptyState>
      </div>
    )
  }

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    const next: typeof errors = {}
    if (password.length < 8) next.password = 'Use at least 8 characters.'
    if (confirm !== password) next.confirm = 'The two passwords do not match.'
    setErrors(next)
    if (Object.keys(next).length) return
    setBusy(true)
    try {
      await api('/api/auth/reset', { base: 'auth', auth: false, json: { token, password } })
      setDone(true)
    } catch (err) {
      if (err instanceof ApiError && err.field === 'password') setErrors({ password: err.message })
      else setErrors({ form: errorMessage(err) })
    } finally { setBusy(false) }
  }

  return (
    <div className="auth-card">
      <div className="auth-logo auth-logo-mobile"><BrandLockup /></div>
      <div>
        <h1>Choose a new password</h1>
        <p className="lead">After this, you will be signed out on every device.</p>
      </div>
      {errors.form && (
        <Callout tone="danger" icon={<TriangleAlert />}>
          {errors.form} <Link to="/forgot-password">Request a new link</Link>
        </Callout>
      )}
      <form className="stack" onSubmit={onSubmit} noValidate>
        <PasswordField label="New password" autoComplete="new-password" autoFocus icon={<LockKeyhole className="input-icon" aria-hidden />}
          value={password} onChange={(e) => setPassword(e.target.value)} error={errors.password} hint="At least 8 characters." />
        <PasswordField label="Confirm new password" autoComplete="new-password" icon={<LockKeyhole className="input-icon" aria-hidden />}
          value={confirm} onChange={(e) => setConfirm(e.target.value)} error={errors.confirm} />
        <Button type="submit" variant="primary" size="lg" block loading={busy}>Update password</Button>
      </form>
    </div>
  )
}
