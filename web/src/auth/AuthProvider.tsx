import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { api, ApiError, configureAuth } from '../lib/api'
import { adoptSession, broadcastAuth, dropSession, onAuthBroadcast, onSessionChange, refreshSession } from '../lib/session'
import { accessTokenStale, msUntilExpiry } from '../lib/token'
import { googleSignOut } from '../lib/google'
import { applyTheme } from '../lib/theme'
import type { AuthConfig, AuthPayload, User } from '../lib/types'

export type AuthStatus = 'booting' | 'authenticated' | 'unauthenticated' | 'unreachable'
export type EndReason = 'expired' | 'signed-out-elsewhere' | 'signed-out' | null

interface AuthContextValue {
  status: AuthStatus
  user: User | null
  config: AuthConfig | null
  endReason: EndReason
  login: (email: string, password: string, remember: boolean) => Promise<AuthPayload>
  signup: (name: string, email: string, password: string) => Promise<AuthPayload>
  googleSignIn: (credential: string) => Promise<AuthPayload>
  logout: () => Promise<void>
  logoutEverywhere: () => Promise<void>
  setUser: (user: User) => void
  reloadUser: () => Promise<void>
  retry: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('booting')
  const [user, setUserState] = useState<User | null>(null)
  const [config, setConfig] = useState<AuthConfig | null>(null)
  const [endReason, setEndReason] = useState<EndReason>(null)
  const [bootNonce, setBootNonce] = useState(0)
  const statusRef = useRef(status)
  statusRef.current = status

  const signedIn = useCallback((payload: AuthPayload) => {
    adoptSession(payload)
    setUserState(payload.user)
    setEndReason(null)
    setStatus('authenticated')
  }, [])

  const signedOut = useCallback((reason: EndReason) => {
    dropSession()
    setUserState(null)
    setEndReason(reason)
    setStatus('unauthenticated')
  }, [])

  // Every API call goes through these: refresh once on 401, then give up cleanly.
  useEffect(() => {
    configureAuth({
      refresh: async () => {
        const p = await refreshSession() // network errors propagate: stay signed in, show an error
        if (p) setUserState(p.user)
        return !!p
      },
      onExpired: () => { if (statusRef.current === 'authenticated') signedOut('expired') },
    })
  }, [signedOut])

  // Boot: public config + silent sign-in from the refresh cookie.
  useEffect(() => {
    let cancelled = false
    setStatus('booting')
    api<AuthConfig>('/api/auth/config', { base: 'auth', auth: false, retries: 3 })
      .then((c) => { if (!cancelled) setConfig(c) })
      .catch(() => { /* Google button stays hidden */ })
    refreshSession()
      .then((p) => { if (cancelled) return; if (p) signedIn(p); else { setUserState(null); setStatus('unauthenticated') } })
      .catch(() => { if (!cancelled) setStatus('unreachable') })
    return () => { cancelled = true }
  }, [bootNonce, signedIn])

  // Refresh a minute before the access token expires, and when a sleeping tab wakes up.
  useEffect(() => {
    if (status !== 'authenticated') return
    let timer = 0
    const schedule = () => {
      clearTimeout(timer)
      timer = window.setTimeout(() => { refreshSession().catch(() => schedule()) }, Math.max(5_000, msUntilExpiry() - 60_000))
    }
    schedule()
    const off = onSessionChange((p) => { if (p) { setUserState(p.user); schedule() } else signedOut('expired') })
    const onVisible = () => { if (document.visibilityState === 'visible' && accessTokenStale(60_000)) refreshSession().catch(() => {}) }
    document.addEventListener('visibilitychange', onVisible)
    return () => { clearTimeout(timer); off(); document.removeEventListener('visibilitychange', onVisible) }
  }, [status, signedOut])

  // Follow sign-in / sign-out in other tabs.
  useEffect(() => onAuthBroadcast((msg) => {
    if (msg.type === 'signed-out' && statusRef.current === 'authenticated') signedOut('signed-out-elsewhere')
    if (msg.type === 'signed-in' && statusRef.current !== 'authenticated') {
      refreshSession().then((p) => p && signedIn(p)).catch(() => {})
    }
  }), [signedIn, signedOut])

  // The account's theme follows the user between devices.
  useEffect(() => { if (user?.preferences.theme) applyTheme(user.preferences.theme) }, [user?.preferences.theme])

  const finish = useCallback((p: AuthPayload) => { signedIn(p); broadcastAuth({ type: 'signed-in' }); return p }, [signedIn])

  const value = useMemo<AuthContextValue>(() => ({
    status, user, config, endReason,
    login: (email, password, remember) =>
      api<AuthPayload>('/api/auth/login', { base: 'auth', auth: false, json: { email, password, remember } }).then(finish),
    signup: (name, email, password) =>
      api<AuthPayload>('/api/auth/signup', { base: 'auth', auth: false, json: { name, email, password, remember: true } }).then(finish),
    googleSignIn: (credential) =>
      api<AuthPayload>('/api/auth/google', { base: 'auth', auth: false, json: { credential } }).then(finish),
    logout: async () => {
      try { await api('/api/auth/logout', { method: 'POST', base: 'auth', auth: false }) } catch { /* signed out locally regardless */ }
      googleSignOut()
      signedOut('signed-out')
      broadcastAuth({ type: 'signed-out' })
    },
    logoutEverywhere: async () => {
      await api('/api/auth/logout-all', { method: 'POST', base: 'auth' })
      googleSignOut()
      signedOut('signed-out')
      broadcastAuth({ type: 'signed-out' })
    },
    setUser: (u) => setUserState(u),
    reloadUser: async () => {
      const r = await api<{ user: User }>('/api/me')
      setUserState(r.user)
    },
    retry: () => setBootNonce((n) => n + 1),
  }), [status, user, config, endReason, finish, signedOut])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}

/** The signed-in user (only call inside a RequireAuth route). */
export function useUser(): User {
  const { user } = useAuth()
  if (!user) throw new Error('useUser called without a signed-in user')
  return user
}

export { ApiError }
