import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { BookOpen, Download, Info, LogOut, Monitor, Moon, Palette, ScanLine, ShieldCheck, Smartphone, Sun, Warehouse } from 'lucide-react'
import { useAuth, useUser } from '../auth/AuthProvider'
import { usePageMeta } from '../components/layout/pageMeta'
import { Button, Card, Callout, Segmented, SelectField, Switch, TextField, cx } from '../components/ui/primitives'
import { useToast } from '../components/ui/feedback'
import { api, errorMessage } from '../lib/api'
import { applyTheme } from '../lib/theme'
import { APP_VERSION, backendLabel } from '../lib/config'
import { CLASS_LABEL, GRADED_CLASSES } from '../lib/format'
import type { Preferences, SetupType, SourceKind, Theme, User } from '../lib/types'
import { isIos, useInstallPrompt } from '../hooks/useInstallPrompt'

/** Saves one preference at a time, optimistically, and rolls back on failure. */
function usePreference() {
  const user = useUser()
  const { setUser } = useAuth()
  const toast = useToast()
  return async (patch: Partial<Preferences>) => {
    const before = user
    setUser({ ...user, preferences: { ...user.preferences, ...patch } })
    try {
      const r = await api<{ user: User }>('/api/me/preferences', { method: 'PATCH', json: patch })
      setUser(r.user)
    } catch (err) {
      setUser(before)
      toast.show({ tone: 'error', message: `Not saved: ${errorMessage(err)}` })
    }
  }
}

function Guide() {
  return (
    <Card title="Counting guide" icon={<BookOpen aria-hidden />} id="guide">
      <div className="guide">
        <p className="secondary small">AquaCount V1 is validated as a <strong>channel counter</strong>: fish swim single-file under a fixed camera and are counted as they cross a line. It is not built to count a crowd of fish from one photo of a basin.</p>
        <h3>Set up once</h3>
        <ul className="checklist">
          <li>Mount the camera directly above the channel and mark its height. Size grading depends on it.</li>
          <li>Frame only the channel. Shade it, and use steady light: glare causes false detections.</li>
          <li>Water should flow from the top of the picture to the bottom.</li>
          <li>Run the empty channel for 2–3 minutes. The count must stay at 0.</li>
        </ul>
        <h3>How fast can fish pass?</h3>
        <p className="small secondary">Each fish must appear in about 6 frames. With <em>F</em> frames per second (shown while counting) and <em>L</em> cm of channel in view, keep fish slower than <strong>F × L ÷ 6</strong> cm/s. At 3 fps and 40 cm, that is 20 cm/s.</p>
        <h3>Calibrate</h3>
        <p className="small secondary">Hand-count at least 5 batches of 150–300 fish, run each through AquaCount, and compare. Reports then show the raw count and a calibrated estimate. Repeat after moving the camera, changing the light, or changing the fish size class.</p>
        <h3>Every count is saved</h3>
        <p className="small secondary">Each run keeps a printable report, a fish-by-fish log (CSV), and a photo of every counted fish for spot checks and disputes. Find them in History.</p>
      </div>
    </Card>
  )
}

export function SettingsPage() {
  const user = useUser()
  const { logout } = useAuth()
  const save = usePreference()
  const location = useLocation()
  const install = useInstallPrompt()
  const p = user.preferences
  const [hatchery, setHatchery] = useState(p.hatchery_name ?? '')
  const [target, setTarget] = useState(p.daily_target ? String(p.daily_target) : '')
  const [theme, setTheme] = useState<Theme>(p.theme ?? 'system')

  usePageMeta({ title: 'Settings' })

  useEffect(() => {
    if (!location.hash) return
    const el = document.getElementById(location.hash.slice(1))
    if (el) setTimeout(() => el.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50)
  }, [location.hash])

  const toggleClass = (k: (typeof GRADED_CLASSES)[number]) => {
    const cur = p.size_focus ?? []
    save({ size_focus: cur.includes(k) ? cur.filter((x) => x !== k) : [...cur, k] })
  }

  return (
    <div className="page page-narrow">
      <Card title="Appearance" icon={<Palette aria-hidden />}>
        <Segmented<Theme> label="Theme" value={theme} onChange={(t) => { setTheme(t); applyTheme(t); save({ theme: t }) }}
          options={[
            { value: 'system', label: 'System', icon: <Monitor aria-hidden /> },
            { value: 'light', label: 'Light', icon: <Sun aria-hidden /> },
            { value: 'dark', label: 'Dark', icon: <Moon aria-hidden /> },
          ]} />
        <div className="divider-list" style={{ marginTop: 8 }}>
          <Switch label="Shorten large numbers" description="Show 12.9K instead of 12,900 on live counters." checked={!!p.compact_numbers} onChange={(v) => save({ compact_numbers: v })} />
          <Switch label="Vibrate on events" description="A short buzz when a count is saved or stops with an error (phones only)." checked={p.haptics !== false} onChange={(v) => save({ haptics: v })} />
        </div>
      </Card>

      <Card title="Hatchery" icon={<Warehouse aria-hidden />} id="hatchery">
        <div className="stack">
          <TextField label="Hatchery or farm name" value={hatchery} maxLength={80} onChange={(e) => setHatchery(e.target.value)}
            onBlur={() => hatchery !== (p.hatchery_name ?? '') && save({ hatchery_name: hatchery })} />
          <SelectField label="Counting setup" value={p.setup_type ?? 'channel'} onChange={(e) => save({ setup_type: e.target.value as SetupType })}>
            <option value="channel">Channel with a fixed camera</option>
            <option value="webcam">USB webcam on a laptop</option>
            <option value="ip_camera">Phone as an IP camera</option>
            <option value="uploads">Recorded videos &amp; photos</option>
          </SelectField>
          <div className="field">
            <span className="field-label">Size classes you grade</span>
            <div className="chips" role="group" aria-label="Size classes you grade">
              {GRADED_CLASSES.map((k) => (
                <button key={k} type="button" className={cx('chip', `class-${k}`)} aria-pressed={!!p.size_focus?.includes(k)} onClick={() => toggleClass(k)}>
                  <span className="swatch" aria-hidden />{CLASS_LABEL[k]}
                </button>
              ))}
            </div>
          </div>
          <TextField label="Daily counting target (fish)" type="number" inputMode="numeric" min={0} step={100} value={target} placeholder="No target"
            onChange={(e) => setTarget(e.target.value)}
            onBlur={() => { const n = Math.max(0, Math.min(10_000_000, Number(target) || 0)); if (n !== (p.daily_target ?? 0)) save({ daily_target: n }) }} />
        </div>
      </Card>

      <Card title="Counting defaults" icon={<ScanLine aria-hidden />}>
        <div className="stack">
          <SelectField label="Open the Count screen on" value={p.default_source ?? 'camera'} onChange={(e) => save({ default_source: e.target.value as SourceKind })}>
            <option value="camera">Station camera</option>
            <option value="upload">Upload a video or photo</option>
            <option value="batch">Photo batch</option>
            <option value="url">Stream or link</option>
          </SelectField>
          <SelectField label="Default station camera" value={String(p.camera_index ?? 0)} onChange={(e) => save({ camera_index: Number(e.target.value) })}
            hint="0 is usually built in, 1 a USB camera. Remembered each time you start one.">
            {Array.from({ length: 10 }, (_, i) => <option key={i} value={i}>Camera {i}</option>)}
          </SelectField>
        </div>
      </Card>

      <Card title="App" icon={<Smartphone aria-hidden />}>
        <div className="stack">
          {install.installed ? (
            <Callout tone="success" icon={<Download />}>AquaCount is installed on this device.</Callout>
          ) : install.canInstall ? (
            <div className="row-between wrap"><span className="secondary small">Install AquaCount for a full-screen app that opens from your home screen.</span>
              <Button variant="primary" icon={<Download />} onClick={() => install.install()}>Install app</Button></div>
          ) : isIos() ? (
            <Callout tone="info" icon={<Info />}>To install on iPhone or iPad: tap <strong>Share</strong>, then <strong>Add to Home Screen</strong>.</Callout>
          ) : (
            <p className="small secondary">Use your browser's menu to install AquaCount as an app on this device.</p>
          )}
          <dl className="kv">
            <dt>Version</dt><dd className="num">{APP_VERSION}</dd>
            <dt>Server</dt><dd className="mono">{backendLabel()}</dd>
            <dt>Signed in as</dt><dd>{user.email}</dd>
          </dl>
          <div className="row wrap">
            {user.role === 'admin' && <Link to="/admin" className="btn btn-outline"><ShieldCheck />Admin &amp; station</Link>}
            <Button variant="danger-text" icon={<LogOut />} onClick={() => logout()}>Sign out</Button>
          </div>
        </div>
      </Card>

      <Guide />
    </div>
  )
}
