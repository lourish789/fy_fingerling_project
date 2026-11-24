import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError, configureAuth } from './api'
import { clearAccessToken, setAccessToken } from './token'

const json = (status: number, body: unknown, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json', ...headers } })

describe('api client', () => {
  const fetchMock = vi.fn()
  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock)
    vi.useFakeTimers({ shouldAdvanceTime: true })
    setAccessToken('token-1', 900)
  })
  afterEach(() => {
    fetchMock.mockReset()
    vi.useRealTimers()
    vi.unstubAllGlobals()
    clearAccessToken()
    configureAuth({ refresh: async () => false, onExpired: () => {} })
  })

  it('sends the bearer token and the client header', async () => {
    fetchMock.mockResolvedValueOnce(json(200, { ok: true }))
    await api('/api/me')
    const [, init] = fetchMock.mock.calls[0]
    expect(init.headers.Authorization).toBe('Bearer token-1')
    expect(init.headers['X-AquaCount-Client']).toBe('web')
  })

  it('retries GETs on 503 (a sleeping free-tier server) and then succeeds', async () => {
    fetchMock.mockResolvedValueOnce(json(503, {})).mockResolvedValueOnce(json(200, { n: 1 }))
    await expect(api<{ n: number }>('/api/runs')).resolves.toEqual({ n: 1 })
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('does not retry POSTs (starting a count twice would be wrong)', async () => {
    fetchMock.mockResolvedValueOnce(json(503, { error: 'busy' }))
    await expect(api('/api/start_camera', { json: {} })).rejects.toBeInstanceOf(ApiError)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('refreshes once on 401 and replays the request with the new token', async () => {
    const refresh = vi.fn(async () => { setAccessToken('token-2', 900); return true })
    configureAuth({ refresh, onExpired: vi.fn() })
    fetchMock.mockResolvedValueOnce(json(401, { code: 'token_expired' })).mockResolvedValueOnce(json(200, { ok: 1 }))
    await expect(api('/api/me')).resolves.toEqual({ ok: 1 })
    expect(refresh).toHaveBeenCalledTimes(1)
    expect(fetchMock.mock.calls[1][1].headers.Authorization).toBe('Bearer token-2')
  })

  it('reports an ended session when the refresh fails', async () => {
    const onExpired = vi.fn()
    configureAuth({ refresh: async () => false, onExpired })
    fetchMock.mockResolvedValue(json(401, { error: 'Sign in to continue.', code: 'unauthorized' }))
    await expect(api('/api/me')).rejects.toMatchObject({ status: 401 })
    expect(onExpired).toHaveBeenCalledTimes(1)
  })

  it('surfaces rate limits with the wait time', async () => {
    fetchMock.mockResolvedValueOnce(json(429, { error: 'Too many attempts.', code: 'rate_limited', retry_after: 42 }, { 'Retry-After': '42' }))
    const err = (await api('/api/auth/login', { json: {}, auth: false }).catch((e: unknown) => e)) as ApiError
    expect(err).toBeInstanceOf(ApiError)
    expect(err.isRateLimited).toBe(true)
    expect(err.retryAfter).toBe(42)
  })

  it('turns a dropped connection into a friendly network error', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))
    const err = (await api('/api/status', { retries: 0 }).catch((e: unknown) => e)) as ApiError
    expect(err).toBeInstanceOf(ApiError)
    expect(err.isNetwork).toBe(true)
  })

  it('keeps the field name so forms can highlight the right input', async () => {
    fetchMock.mockResolvedValueOnce(json(409, { error: 'Taken', code: 'email_taken', field: 'email' }))
    const err = (await api('/api/auth/signup', { json: {}, auth: false }).catch((e: unknown) => e)) as ApiError
    expect(err.field).toBe('email')
    expect(err.code).toBe('email_taken')
  })
})
