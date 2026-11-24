import { useEffect, useRef, useState } from 'react'
import { renderGoogleButton } from '../lib/google'
import { resolvedTheme } from '../lib/theme'
import { useOnline } from '../hooks/useOnline'

/**
 * The official "Continue with Google" button (Google requires its own rendering).
 * Renders nothing when this server has no Google client ID configured.
 */
export function GoogleButton({ clientId, onCredential, text = 'continue_with', disabled }: {
  clientId: string | null | undefined
  onCredential: (credential: string) => void
  text?: 'continue_with' | 'signup_with' | 'signin_with'
  disabled?: boolean
}) {
  const ref = useRef<HTMLDivElement>(null)
  const online = useOnline()
  const [failed, setFailed] = useState<string | null>(null)
  const cb = useRef(onCredential)
  cb.current = onCredential

  useEffect(() => {
    const el = ref.current
    if (!el || !clientId || !online) return
    let cancelled = false
    const width = Math.min(400, Math.max(220, Math.round(el.getBoundingClientRect().width)))
    renderGoogleButton(el, clientId, (c) => cb.current(c), {
      type: 'standard', theme: resolvedTheme() === 'dark' ? 'filled_black' : 'outline', size: 'large',
      text, shape: 'pill', logo_alignment: 'center', width,
    }).then(() => { if (!cancelled) setFailed(null) })
      .catch((e: Error) => { if (!cancelled) setFailed(e.message) })
    return () => { cancelled = true }
  }, [clientId, online, text])

  if (!clientId) return null
  return (
    <div className="google-btn" aria-disabled={disabled || undefined} style={disabled ? { pointerEvents: 'none', opacity: 0.6 } : undefined}>
      <div ref={ref} style={{ width: '100%', minHeight: 44, display: 'flex', justifyContent: 'center', colorScheme: 'normal' }} />
      {(!online || failed) && (
        <p className="xsmall muted center" style={{ marginTop: 6 }}>
          {!online ? 'Google sign-in needs an internet connection.' : failed}
        </p>
      )}
    </div>
  )
}
