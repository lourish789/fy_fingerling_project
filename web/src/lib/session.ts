import { api, ApiError } from './api'
import { clearAccessToken, setAccessToken } from './token'
import type { AuthPayload } from './types'

/**
 * Refreshing the session.
 *
 * - One refresh at a time per tab (single-flight promise).
 * - One at a time across tabs (Web Locks): every tab shares the refresh cookie,
 *   and the server rotates it on each use, so two tabs refreshing at the same
 *   instant would otherwise look like a stolen token.
 * - Sign-in and sign-out are broadcast so every open tab follows.
 */

type AuthMessage = { type: 'signed-in' } | { type: 'signed-out' }
const channel: BroadcastChannel | null = typeof BroadcastChannel !== 'undefined' ? new BroadcastChannel('aquacount-auth') : null

export function broadcastAuth(msg: AuthMessage): void {
  try { channel?.postMessage(msg) } catch { /* closed channel */ }
}

export function onAuthBroadcast(fn: (msg: AuthMessage) => void): () => void {
  if (!channel) return () => {}
  const handler = (e: MessageEvent<AuthMessage>) => fn(e.data)
  channel.addEventListener('message', handler)
  return () => channel.removeEventListener('message', handler)
}

let inflight: Promise<AuthPayload | null> | null = null
let lastPayload: AuthPayload | null = null
const listeners = new Set<(p: AuthPayload | null) => void>()

/** Notified after every refresh attempt (null = signed out). */
export function onSessionChange(fn: (p: AuthPayload | null) => void): () => void {
  listeners.add(fn)
  return () => { listeners.delete(fn) }
}

async function doRefresh(): Promise<AuthPayload | null> {
  try {
    const payload = await api<AuthPayload>('/api/auth/refresh', { method: 'POST', base: 'auth', auth: false, retries: 1 })
    setAccessToken(payload.access_token, payload.expires_in)
    lastPayload = payload
    return payload
  } catch (err) {
    if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
      clearAccessToken()
      lastPayload = null
      return null
    }
    throw err // network trouble: the caller decides (we stay signed in meanwhile)
  }
}

/** Get a fresh access token from the refresh cookie. Resolves null when signed out; rejects on network errors. */
export function refreshSession(): Promise<AuthPayload | null> {
  if (inflight) return inflight
  const locks = typeof navigator !== 'undefined' ? navigator.locks : undefined
  inflight = (locks ? locks.request('aquacount-refresh', doRefresh) : doRefresh())
    .then((p) => { listeners.forEach((l) => l(p)); return p })
    .finally(() => { inflight = null })
  return inflight
}

export function lastSession(): AuthPayload | null {
  return lastPayload
}

export function adoptSession(payload: AuthPayload): void {
  setAccessToken(payload.access_token, payload.expires_in)
  lastPayload = payload
}

export function dropSession(): void {
  clearAccessToken()
  lastPayload = null
}
