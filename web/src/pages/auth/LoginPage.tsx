import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Info, LockKeyhole, Mail, TriangleAlert } from 'lucide-react'
import { useAuth, ApiError } from '../../auth/AuthProvider'
import { GoogleButton } from '../../components/GoogleButton'
import { BrandLockup } from '../../components/BrandMark'
import { Button, Callout, PasswordField, TextField } from '../../components/ui/primitives'
import { useCountdown } from './AuthLayout'

const REASONS: Record<string, string> = {
  expired: 'Your session ended. Sign in again to carry on where you left off.',
  'signed-out-elsewhere': 'You signed out in another tab.',
}

export function LoginPage() {
  const { login, googleSignIn, config } = useAuth()
  const [params] = useSearchParams()
  const reason = params.get('reason')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [remember, setRemember] = useState(true)
  const [errors, setErrors] = useState<{ email?: string; password?: string; form?: string }>({})
  const [busy, setBusy] = useState(false)
  const [lockedUntil, setLockedUntil] = useState<number | null>(null)
  const wait = useCountdown(lockedUntil)
  const emailRef = useRef<HTMLInputElement>(null)

  useEffect(() => { document.title = 'Sign in · AquaCount' }, [])

  const fail = (err: unknown) => {
    if (err instanceof ApiError) {
      if (err.isRateLimited && err.retryAfter) setLockedUntil(Date.now() + err.retryAfter * 1000)
      if (err.field === 'email' || err.field === 'password') setErrors({ [err.field]: err.message })
      else setErrors({ form: err.message })
    } else setErrors({ form: 'Something went wrong. Try again.' })
  }

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    const next: typeof errors = {}
    if (!email.trim()) next.email = 'Enter your email address.'
    if (!password) next.password = 'Enter your password.'
    setErrors(next)
    if (next.email || next.password) { (next.email ? emailRef.current : null)?.focus(); return }
    setBusy(true)
    try { await login(email.trim(), password, remember) } // PublicOnly redirects once signed in
    catch (err) { fail(err); setBusy(false) }
  }

  const onGoogle = async (credential: string) => {
    setErrors({})
    setBusy(true)
    try { await googleSignIn(credential) } catch (err) { fail(err); setBusy(false) }
  }

  return (
    <div className="auth-card">
      <div className="auth-logo auth-logo-mobile"><BrandLockup /></div>
      <div>
        <h1>Welcome back</h1>
        <p className="lead">Sign in to count, review batches and download reports.</p>
      </div>

      {reason && REASONS[reason] && <Callout tone="info" icon={<Info />}>{REASONS[reason]}</Callout>}
      {errors.form && <Callout tone="danger" icon={<TriangleAlert />}>{errors.form}{wait > 0 && <> Try again in <strong className="num">{wait}s</strong>.</>}</Callout>}

      {config?.google_client_id && (
        <>
          <GoogleButton clientId={config.google_client_id} onCredential={onGoogle} disabled={busy} />
          <div className="divider-label">or with email</div>
        </>
      )}

      <form className="stack" onSubmit={onSubmit} noValidate>
        <TextField ref={emailRef} label="Email" type="email" autoComplete="email" inputMode="email" autoCapitalize="off"
          icon={<Mail className="input-icon" aria-hidden />} value={email} onChange={(e) => setEmail(e.target.value)} error={errors.email} required />
        <PasswordField label="Password" autoComplete="current-password" icon={<LockKeyhole className="input-icon" aria-hidden />}
          value={password} onChange={(e) => setPassword(e.target.value)} error={errors.password} required
          aside={<Link to="/forgot-password" className="small">Forgot password?</Link>} />
        <label className="checkbox">
          <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
          Keep me signed in on this device
        </label>
        <Button type="submit" variant="primary" size="lg" block loading={busy} disabled={wait > 0}>
          {wait > 0 ? `Try again in ${wait}s` : 'Sign in'}
        </Button>
      </form>

      {config?.signup_enabled !== false && (
        <p className="auth-foot">New to AquaCount? <Link to={`/signup${params.get('next') ? `?next=${encodeURIComponent(params.get('next')!)}` : ''}`}>Create an account</Link></p>
      )}
    </div>
  )
}
