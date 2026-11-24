import { useEffect, useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { LockKeyhole, Mail, TriangleAlert, UserRound } from 'lucide-react'
import { useAuth, ApiError } from '../../auth/AuthProvider'
import { GoogleButton } from '../../components/GoogleButton'
import { BrandLockup } from '../../components/BrandMark'
import { Button, Callout, EmptyState, PasswordField, TextField } from '../../components/ui/primitives'
import { passwordStrength } from '../../lib/format'
import { useCountdown } from './AuthLayout'
import { DEMO } from '../../lib/config'

const STRENGTH_LABEL = ['', 'Too short', 'Okay', 'Good', 'Strong']

export function SignupPage() {
  const { signup, googleSignIn, config } = useAuth()
  const [params] = useSearchParams()
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [errors, setErrors] = useState<{ name?: string; email?: string; password?: string; form?: string }>({})
  const [busy, setBusy] = useState(false)
  const [lockedUntil, setLockedUntil] = useState<number | null>(null)
  const wait = useCountdown(lockedUntil)
  const strength = passwordStrength(password)

  useEffect(() => { document.title = 'Create account · AquaCount' }, [])

  const fail = (err: unknown) => {
    if (err instanceof ApiError) {
      if (err.isRateLimited && err.retryAfter) setLockedUntil(Date.now() + err.retryAfter * 1000)
      if (err.field === 'name' || err.field === 'email' || err.field === 'password') setErrors({ [err.field]: err.message })
      else setErrors({ form: err.message })
    } else setErrors({ form: 'Something went wrong. Try again.' })
  }

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    const next: typeof errors = {}
    if (!name.trim()) next.name = 'Enter your name.'
    if (!/^\S+@\S+\.\S+$/.test(email.trim())) next.email = 'Enter a valid email address.'
    if (password.length < 8) next.password = 'Use at least 8 characters.'
    setErrors(next)
    if (Object.keys(next).length) return
    setBusy(true)
    try { await signup(name.trim(), email.trim(), password) } catch (err) { fail(err); setBusy(false) }
  }

  const onGoogle = async (credential: string) => {
    setErrors({})
    setBusy(true)
    try { await googleSignIn(credential) } catch (err) { fail(err); setBusy(false) }
  }

  if (config && !config.signup_enabled) {
    return (
      <div className="auth-card">
        <div className="auth-logo auth-logo-mobile"><BrandLockup /></div>
        <EmptyState icon={<UserRound />} title="Accounts are by invitation"
          action={<Link className="btn btn-primary" to="/login">Back to sign in</Link>}>
          This station does not allow new sign-ups. Ask the station administrator to add you.
        </EmptyState>
      </div>
    )
  }

  return (
    <div className="auth-card">
      <div className="auth-logo auth-logo-mobile"><BrandLockup /></div>
      <div>
        <h1>Create your account</h1>
        <p className="lead">Your counts, reports and settings follow you to any device.</p>
      </div>

      {errors.form && <Callout tone="danger" icon={<TriangleAlert />}>{errors.form}{wait > 0 && <> Try again in <strong className="num">{wait}s</strong>.</>}</Callout>}

      {(config?.google_client_id || DEMO) && (
        <>
          <GoogleButton clientId={config?.google_client_id} onCredential={onGoogle} text="signup_with" disabled={busy} />
          <div className="divider-label">or with email</div>
        </>
      )}

      <form className="stack" onSubmit={onSubmit} noValidate>
        <TextField label="Full name" autoComplete="name" icon={<UserRound className="input-icon" aria-hidden />}
          value={name} onChange={(e) => setName(e.target.value)} error={errors.name} required />
        <TextField label="Email" type="email" autoComplete="email" inputMode="email" autoCapitalize="off"
          icon={<Mail className="input-icon" aria-hidden />} value={email} onChange={(e) => setEmail(e.target.value)} error={errors.email} required />
        <div className="stack-sm">
          <PasswordField label="Password" autoComplete="new-password" icon={<LockKeyhole className="input-icon" aria-hidden />}
            value={password} onChange={(e) => setPassword(e.target.value)} error={errors.password}
            hint="At least 8 characters. A short phrase is easier to remember and harder to guess." required />
          {password && (
            <div className="row" style={{ gap: 10 }} aria-live="polite">
              <div className="strength grow" data-level={strength} aria-hidden><span /><span /><span /><span /></div>
              <span className="xsmall muted" style={{ minWidth: 64, textAlign: 'right' }}>{STRENGTH_LABEL[strength]}</span>
            </div>
          )}
        </div>
        <Button type="submit" variant="primary" size="lg" block loading={busy} disabled={wait > 0}>Create account</Button>
        <p className="xsmall muted center">The first account on a new station becomes its administrator.</p>
      </form>

      <p className="auth-foot">Already have an account? <Link to={`/login${params.get('next') ? `?next=${encodeURIComponent(params.get('next')!)}` : ''}`}>Sign in</Link></p>
    </div>
  )
}
