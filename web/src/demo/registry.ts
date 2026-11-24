/**
 * Demo mode hook-up. main.tsx loads ./backend (dynamically, only in demo builds)
 * and registers it here; the API client, uploads, socket and file links ask for it.
 * In normal builds nothing is registered and this module is inert.
 */
import type * as Backend from './backend'

export const DEMO_EMAIL = 'demo@aquacount.app'
export const DEMO_PASSWORD = 'fingerlings'

let backend: typeof Backend | null = null
export function setDemoBackend(m: typeof Backend): void { backend = m }
export function demoBackend(): typeof Backend | null { return backend }
