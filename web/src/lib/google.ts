/**
 * Google Identity Services ("Continue with Google").
 * The button hands back an ID token (credential) that the backend verifies
 * against Google's published keys; no Google secret ever reaches the browser.
 */

interface CredentialResponse { credential: string }
export interface GsiButtonOptions {
  type?: 'standard' | 'icon'
  theme?: 'outline' | 'filled_blue' | 'filled_black'
  size?: 'large' | 'medium' | 'small'
  text?: 'signin_with' | 'signup_with' | 'continue_with' | 'signin'
  shape?: 'rectangular' | 'pill' | 'circle' | 'square'
  logo_alignment?: 'left' | 'center'
  width?: number
}
interface GoogleAccountsId {
  initialize(cfg: {
    client_id: string
    callback: (r: CredentialResponse) => void
    ux_mode?: 'popup' | 'redirect'
    auto_select?: boolean
    itp_support?: boolean
    cancel_on_tap_outside?: boolean
  }): void
  renderButton(el: HTMLElement, opts: GsiButtonOptions): void
  disableAutoSelect(): void
}
declare global {
  interface Window { google?: { accounts: { id: GoogleAccountsId } } }
}

const SRC = 'https://accounts.google.com/gsi/client'
let loader: Promise<GoogleAccountsId> | null = null

export function loadGoogleIdentity(): Promise<GoogleAccountsId> {
  if (window.google?.accounts?.id) return Promise.resolve(window.google.accounts.id)
  if (loader) return loader
  loader = new Promise<GoogleAccountsId>((resolve, reject) => {
    const s = document.createElement('script')
    s.src = SRC
    s.async = true
    s.onload = () => (window.google?.accounts?.id ? resolve(window.google.accounts.id) : reject(new Error('Google sign-in did not load.')))
    s.onerror = () => { loader = null; s.remove(); reject(new Error('Google sign-in could not load. Are you offline?')) }
    document.head.appendChild(s)
  })
  return loader
}

let currentCallback: ((credential: string) => void) | null = null
let initializedFor: string | null = null

/** Render the official button into `el`; `onCredential` receives the ID token. */
export async function renderGoogleButton(el: HTMLElement, clientId: string, onCredential: (credential: string) => void, opts: GsiButtonOptions): Promise<void> {
  const gsi = await loadGoogleIdentity()
  currentCallback = onCredential
  if (initializedFor !== clientId) {
    gsi.initialize({
      client_id: clientId,
      callback: (r) => currentCallback?.(r.credential),
      ux_mode: 'popup',
      auto_select: false,
      itp_support: true,
      cancel_on_tap_outside: true,
    })
    initializedFor = clientId
  }
  el.replaceChildren()
  gsi.renderButton(el, opts)
}

export function googleSignOut(): void {
  try { window.google?.accounts?.id?.disableAutoSelect() } catch { /* not loaded */ }
}
