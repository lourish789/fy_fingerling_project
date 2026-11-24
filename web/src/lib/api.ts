import { API_BASE, AUTH_BASE } from './config'
import { accessTokenStale, getAccessToken } from './token'

/** Custom header the backend requires on cookie-authenticated calls (blocks cross-site form posts). */
export const CLIENT_HEADER = { 'X-AquaCount-Client': 'web' }

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly field?: string
  readonly retryAfter?: number
  readonly data?: Record<string, unknown>

  constructor(message: string, status: number, code: string, extra: { field?: string; retryAfter?: number; data?: Record<string, unknown> } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.field = extra.field
    this.retryAfter = extra.retryAfter
    this.data = extra.data
  }

  get isNetwork() { return this.status === 0 }
  get isRateLimited() { return this.status === 429 }
}

interface AuthHooks {
  /** Get a new access token from the refresh cookie. Resolves false when signed out. */
  refresh: () => Promise<boolean>
  /** Called when a request could not be authorised even after a refresh. */
  onExpired: () => void
}
let hooks: AuthHooks | null = null
export function configureAuth(h: AuthHooks): void { hooks = h }

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE'
  json?: unknown
  body?: BodyInit
  /** Send the bearer token (default true). Sign-in calls pass false. */
  auth?: boolean
  /** 'auth' → AUTH_BASE with cookies; default → API_BASE. */
  base?: 'api' | 'auth'
  /** Retries for network errors and 502/503/504 (default: 2 for GET, 0 otherwise). */
  retries?: number
  signal?: AbortSignal
  headers?: Record<string, string>
}

const sleep = (ms: number, signal?: AbortSignal) => new Promise<void>((resolve, reject) => {
  const t = setTimeout(resolve, ms)
  signal?.addEventListener('abort', () => { clearTimeout(t); reject(new DOMException('Aborted', 'AbortError')) }, { once: true })
})

export function backoffMs(attempt: number, retryAfterSeconds?: number): number {
  if (retryAfterSeconds && retryAfterSeconds > 0) return Math.min(retryAfterSeconds * 1000, 15_000)
  const base = Math.min(8000, 600 * 2 ** attempt)
  return base / 2 + Math.random() * (base / 2) // jitter, so many phones do not retry in lockstep
}

function parseRetryAfter(res: Response): number | undefined {
  const raw = res.headers.get('Retry-After')
  if (!raw) return undefined
  const n = Number(raw)
  return Number.isFinite(n) ? n : undefined
}

const FRIENDLY: Record<number, string> = {
  400: 'Something in the request was not right.',
  401: 'Please sign in again.',
  403: 'You do not have permission to do that.',
  404: 'That could not be found.',
  409: 'That conflicts with something already there.',
  413: 'That file is too large.',
  429: 'Too many attempts. Please wait a moment.',
  500: 'The server hit a problem. Try again shortly.',
  502: 'The server is starting up or unreachable. Try again shortly.',
  503: 'The server is busy or starting up. Try again shortly.',
  504: 'The server took too long to answer. Try again shortly.',
}

export async function api<T = unknown>(path: string, opts: RequestOptions = {}): Promise<T> {
  const method = opts.method ?? (opts.json !== undefined ? 'POST' : 'GET')
  const base = opts.base === 'auth' ? AUTH_BASE : API_BASE
  const maxRetries = opts.retries ?? (method === 'GET' ? 2 : 0)
  const wantsAuth = opts.auth !== false
  let attempt = 0
  let refreshed = false

  for (;;) {
    if (wantsAuth && hooks && !refreshed && accessTokenStale()) {
      refreshed = true
      if (!(await hooks.refresh())) {
        hooks.onExpired()
        throw new ApiError('Your session has ended. Please sign in again.', 401, 'session_expired')
      }
    }

    const headers: Record<string, string> = { ...CLIENT_HEADER, ...opts.headers }
    if (opts.json !== undefined) headers['Content-Type'] = 'application/json'
    const token = wantsAuth ? getAccessToken() : null
    if (token) headers.Authorization = `Bearer ${token}`

    let res: Response
    try {
      res = await fetch(base + path, {
        method,
        headers,
        body: opts.json !== undefined ? JSON.stringify(opts.json) : opts.body,
        credentials: opts.base === 'auth' ? 'include' : 'same-origin',
        signal: opts.signal,
      })
    } catch (err) {
      if (opts.signal?.aborted) throw err
      if (attempt < maxRetries) { await sleep(backoffMs(attempt++), opts.signal); continue }
      throw new ApiError('Cannot reach the AquaCount server. Check your connection and try again.', 0, 'network')
    }

    if (res.status === 401 && wantsAuth && hooks) {
      if (!refreshed) {
        refreshed = true
        if (await hooks.refresh()) continue
      }
      hooks.onExpired()
    }
    const retryAfter = parseRetryAfter(res)
    if ([502, 503, 504].includes(res.status) && attempt < maxRetries) {
      await sleep(backoffMs(attempt++, retryAfter), opts.signal)
      continue
    }

    let data: unknown = null
    const type = res.headers.get('Content-Type') || ''
    if (res.status !== 204) {
      data = type.includes('application/json') ? await res.json().catch(() => null) : await res.text().catch(() => null)
    }
    if (!res.ok) {
      const body = (data && typeof data === 'object' ? data : {}) as Record<string, unknown>
      throw new ApiError(
        typeof body.error === 'string' ? body.error : FRIENDLY[res.status] ?? `Request failed (${res.status}).`,
        res.status,
        typeof body.code === 'string' ? body.code : `http_${res.status}`,
        { field: typeof body.field === 'string' ? body.field : undefined, retryAfter: retryAfter ?? (typeof body.retry_after === 'number' ? body.retry_after : undefined), data: body },
      )
    }
    return data as T
  }
}

/** Absolute URL for a backend path (downloads, images, the socket). */
export function apiUrl(path: string): string {
  return (API_BASE || '') + path
}

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message
  if (err instanceof Error) return err.message
  return 'Something went wrong.'
}
