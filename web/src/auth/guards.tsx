import { useEffect, useState } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { CloudOff } from 'lucide-react'
import { useAuth } from './AuthProvider'
import { BrandMark } from '../components/BrandMark'
import { Button } from '../components/ui/primitives'

/** Shown while the session is restored. After a few seconds, explains a sleeping free-tier server. */
export function BootScreen() {
  const [slow, setSlow] = useState(false)
  useEffect(() => { const t = setTimeout(() => setSlow(true), 3500); return () => clearTimeout(t) }, [])
  return (
    <div className="fullscreen-state" role="status" aria-live="polite">
      <div className="state">
        <BrandMark className="boot-mark" />
        <h3>{slow ? 'Waking up the counting server…' : 'Opening AquaCount…'}</h3>
        {slow && <p>Hosted servers sleep when idle and can take up to a minute to start. Your data is safe.</p>}
      </div>
    </div>
  )
}

export function ServerUnreachable() {
  const { retry } = useAuth()
  const [seconds, setSeconds] = useState(15)
  useEffect(() => {
    const t = setInterval(() => setSeconds((s) => (s <= 1 ? 0 : s - 1)), 1000)
    return () => clearInterval(t)
  }, [])
  useEffect(() => { if (seconds === 0) retry() }, [seconds, retry])
  return (
    <div className="fullscreen-state">
      <div className="state state-error" role="alert">
        <div className="state-icon"><CloudOff /></div>
        <h3>Cannot reach the AquaCount server</h3>
        <p>Check that this device is online, or on the same Wi-Fi as the hatchery laptop. Trying again in {seconds} s.</p>
        <div className="row"><Button variant="primary" onClick={retry}>Try now</Button></div>
      </div>
    </div>
  )
}

/** Protected routes: restores the session, or sends the visitor to sign in and back again afterwards. */
export function RequireAuth() {
  const { status, endReason } = useAuth()
  const location = useLocation()
  if (status === 'booting') return <BootScreen />
  if (status === 'unreachable') return <ServerUnreachable />
  if (status === 'unauthenticated') {
    const next = location.pathname + location.search
    const params = new URLSearchParams()
    if (next && next !== '/') params.set('next', next)
    if (endReason === 'expired' || endReason === 'signed-out-elsewhere') params.set('reason', endReason)
    const qs = params.toString()
    return <Navigate to={`/login${qs ? `?${qs}` : ''}`} replace />
  }
  return <Outlet />
}

/** First-time users finish onboarding before reaching the app. */
export function RequireOnboarded() {
  const { user } = useAuth()
  if (user && !user.onboarded) return <Navigate to="/welcome" replace />
  return <Outlet />
}

/** Sign-in pages: signed-in visitors go straight to where they were heading. */
export function PublicOnly() {
  const { status, user } = useAuth()
  const location = useLocation()
  if (status === 'booting') return <BootScreen />
  if (status === 'authenticated' && user) {
    const next = new URLSearchParams(location.search).get('next')
    const safeNext = next && next.startsWith('/') && !next.startsWith('//') ? next : '/'
    return <Navigate to={user.onboarded ? safeNext : '/welcome'} replace />
  }
  return <Outlet />
}

export function RequireRole({ role }: { role: 'admin' }) {
  const { user } = useAuth()
  if (user?.role !== role) return <Navigate to="/" replace />
  return <Outlet />
}
