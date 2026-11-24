const trimSlash = (s: string | undefined) => (s ?? '').trim().replace(/\/+$/, '')

/** Backend for data, uploads and the live stream. '' = same origin (hatchery laptop, dev proxy). */
export const API_BASE = trimSlash(import.meta.env.VITE_API_URL)

/** Backend for /api/auth. '' = same origin; on Vercel it is proxied so the refresh cookie is first-party. */
export const AUTH_BASE = trimSlash(import.meta.env.VITE_AUTH_URL)

export const APP_VERSION = '2.0.0'

/** Demo build: simulated station and sample data in the browser (see src/demo). */
export const DEMO = import.meta.env.VITE_DEMO === '1'

/** Shown in About: where this app talks to. */
export function backendLabel(): string {
  if (API_BASE) return API_BASE.replace(/^https?:\/\//, '')
  return typeof window !== 'undefined' ? window.location.host : 'this server'
}
