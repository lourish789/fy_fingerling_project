import { useEffect, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, ArrowRight, Camera, Check, Film, Monitor, Moon, Smartphone, Sun, Waves } from 'lucide-react'
import { useAuth, useUser } from '../auth/AuthProvider'
import { api, errorMessage } from '../lib/api'
import { applyTheme } from '../lib/theme'
import { CLASS_LABEL, GRADED_CLASSES } from '../lib/format'
import type { Preferences, SetupType, Theme, User } from '../lib/types'
import { BrandLockup } from '../components/BrandMark'
import { DemoBanner } from '../components/DemoBanner'
import { Button, Callout, Segmented, TextField, cx } from '../components/ui/primitives'
import { TriangleAlert } from 'lucide-react'

const SETUPS: { value: SetupType; title: string; body: string; icon: ReactNode; recommended?: boolean }[] = [
  { value: 'channel', title: 'Channel with a fixed camera', body: 'Fish swim single-file under a mounted camera. The validated setup.', icon: <Waves />, recommended: true },
  { value: 'webcam', title: 'USB webcam on a laptop', body: 'A camera plugged into the hatchery computer.', icon: <Camera /> },
  { value: 'ip_camera', title: 'Phone as a camera', body: 'An IP-camera app streams to the counter over Wi-Fi.', icon: <Smartphone /> },
  { value: 'uploads', title: 'Recorded videos & photos', body: 'Upload clips or batches of photos to count.', icon: <Film /> },
]

const STEPS = ['About you', 'Your hatchery', 'Preferences']

export function OnboardingPage() {
  const user = useUser()
  const { setUser, logout } = useAuth()
  const navigate = useNavigate()
  const [step, setStep] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [name, setName] = useState(user.name)
  const [prefs, setPrefs] = useState<Preferences>({
    role_title: user.preferences.role_title ?? '',
    hatchery_name: user.preferences.hatchery_name ?? '',
    setup_type: user.preferences.setup_type ?? 'channel',
    size_focus: user.preferences.size_focus ?? [...GRADED_CLASSES],
    daily_target: user.preferences.daily_target ?? 0,
    theme: user.preferences.theme ?? 'system',
  })
  const set = <K extends keyof Preferences>(k: K, v: Preferences[K]) => setPrefs((p) => ({ ...p, [k]: v }))

  useEffect(() => { document.title = 'Welcome · AquaCount' }, [])
  useEffect(() => { if (user.onboarded) navigate('/', { replace: true }) }, [user.onboarded, navigate])

  const finish = async (skip = false) => {
    setBusy(true)
    setError(null)
    try {
      const body = skip ? {} : { ...prefs, name: name.trim() || user.name, default_source: prefs.setup_type === 'uploads' ? 'upload' : prefs.setup_type === 'ip_camera' ? 'url' : 'camera' }
      const r = await api<{ user: User }>('/api/me/onboarding', { json: body })
      setUser(r.user)
      navigate('/', { replace: true })
    } catch (err) {
      setError(errorMessage(err))
      setBusy(false)
    }
  }

  const toggleClass = (k: (typeof GRADED_CLASSES)[number]) => {
    const cur = prefs.size_focus ?? []
    set('size_focus', cur.includes(k) ? cur.filter((x) => x !== k) : [...cur, k])
  }

  return (
    <div className="onboarding">
      <DemoBanner />
      <header className="onboarding-head">
        <div className="row"><BrandLockup sub={false} /></div>
        <button className="link-btn small" onClick={() => finish(true)} disabled={busy}>Skip for now</button>
      </header>

      <div className="onboarding-body">
        <ol className="steps" aria-label="Setup progress">
          {STEPS.map((s, i) => (
            <li key={s} className={cx('step', i < step && 'done', i === step && 'current')} aria-current={i === step ? 'step' : undefined}>
              <span className="step-dot">{i < step ? <Check aria-hidden /> : i + 1}</span><span className="step-label">{s}</span>
            </li>
          ))}
        </ol>

        {error && <Callout tone="danger" icon={<TriangleAlert />}>{error}</Callout>}

        {step === 0 && (
          <section className="stack" aria-labelledby="ob-0">
            <div>
              <h1 id="ob-0">Welcome to AquaCount</h1>
              <p className="secondary" style={{ marginTop: 6 }}>A few details make your reports and history clearer. You can change all of this later.</p>
            </div>
            <TextField label="Your name" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} hint="Shown on runs you start, so the team knows who counted." />
            <TextField label="Your role (optional)" placeholder="e.g. Hatchery manager, Counting operator" value={prefs.role_title} onChange={(e) => set('role_title', e.target.value)} maxLength={60} />
          </section>
        )}

        {step === 1 && (
          <section className="stack" aria-labelledby="ob-1">
            <div>
              <h1 id="ob-1">Your hatchery</h1>
              <p className="secondary" style={{ marginTop: 6 }}>How do fish reach the camera?</p>
            </div>
            <TextField label="Hatchery or farm name" placeholder="e.g. Lekki Fish Farm" value={prefs.hatchery_name} onChange={(e) => set('hatchery_name', e.target.value)} maxLength={80} />
            <div className="choice-grid" role="radiogroup" aria-label="Counting setup">
              {SETUPS.map((s) => (
                <button key={s.value} type="button" role="radio" aria-checked={prefs.setup_type === s.value}
                  className={cx('choice', prefs.setup_type === s.value && 'selected')} onClick={() => set('setup_type', s.value)}>
                  <span className="choice-icon">{s.icon}</span>
                  <span className="grow">
                    <span className="choice-title">{s.title}{s.recommended && <span className="badge badge-accent" style={{ marginLeft: 8 }}>Recommended</span>}</span>
                    <span className="choice-body">{s.body}</span>
                  </span>
                  <span className="choice-check" aria-hidden><Check /></span>
                </button>
              ))}
            </div>
            <div className="field">
              <span className="field-label">Size classes you grade</span>
              <div className="chips" role="group" aria-label="Size classes you grade">
                {GRADED_CLASSES.map((k) => (
                  <button key={k} type="button" className={cx('chip', `class-${k}`)} aria-pressed={prefs.size_focus?.includes(k)} onClick={() => toggleClass(k)}>
                    <span className="swatch" aria-hidden />{CLASS_LABEL[k]}
                  </button>
                ))}
              </div>
              <span className="field-hint">Highlighted on your live counts. Every class is still counted.</span>
            </div>
          </section>
        )}

        {step === 2 && (
          <section className="stack" aria-labelledby="ob-2">
            <div>
              <h1 id="ob-2">Preferences</h1>
              <p className="secondary" style={{ marginTop: 6 }}>Set a daily goal to track progress on your home screen.</p>
            </div>
            <TextField label="Daily counting target (fish)" type="number" inputMode="numeric" min={0} step={100}
              value={prefs.daily_target || ''} placeholder="e.g. 10000"
              onChange={(e) => set('daily_target', Math.max(0, Math.min(10_000_000, Number(e.target.value) || 0)))}
              hint="Leave empty for no target." />
            <div className="field">
              <span className="field-label">Appearance</span>
              <Segmented<Theme> label="Theme" value={prefs.theme ?? 'system'}
                onChange={(t) => { set('theme', t); applyTheme(t) }}
                options={[
                  { value: 'system', label: 'System', icon: <Monitor aria-hidden /> },
                  { value: 'light', label: 'Light', icon: <Sun aria-hidden /> },
                  { value: 'dark', label: 'Dark', icon: <Moon aria-hidden /> },
                ]} />
              <span className="field-hint">Dark is easier on the eyes beside a bright channel, and saves battery.</span>
            </div>
          </section>
        )}
      </div>

      <footer className="onboarding-foot">
        {step > 0 ? <Button variant="ghost" icon={<ArrowLeft />} onClick={() => setStep((s) => s - 1)} disabled={busy}>Back</Button>
          : <Button variant="ghost" onClick={() => logout()} disabled={busy}>Sign out</Button>}
        {step < STEPS.length - 1
          ? <Button variant="primary" size="lg" onClick={() => setStep((s) => s + 1)}>Continue<ArrowRight /></Button>
          : <Button variant="primary" size="lg" loading={busy} onClick={() => finish(false)}>Start counting</Button>}
      </footer>
    </div>
  )
}
