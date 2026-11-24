/**
 * The access token lives only in memory: it is never written to storage, so
 * a script injected into the page later cannot read a long-lived credential.
 * The refresh token is an httpOnly cookie the page cannot see at all.
 */
let accessToken: string | null = null
let expiresAt = 0

export function setAccessToken(token: string, expiresInSeconds: number): void {
  accessToken = token
  expiresAt = Date.now() + expiresInSeconds * 1000
}

export function getAccessToken(): string | null {
  return accessToken
}

export function clearAccessToken(): void {
  accessToken = null
  expiresAt = 0
}

/** True when the token is missing or will expire within `marginMs`. */
export function accessTokenStale(marginMs = 30_000): boolean {
  return !accessToken || Date.now() > expiresAt - marginMs
}

export function msUntilExpiry(): number {
  return Math.max(0, expiresAt - Date.now())
}
