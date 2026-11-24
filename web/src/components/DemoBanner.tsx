import { FlaskConical } from 'lucide-react'
import { DEMO } from '../lib/config'
import { demoBackend } from '../demo/registry'

/** Always visible in demo builds, so a preview is never mistaken for real counts. */
export function DemoBanner() {
  if (!DEMO) return null
  const reset = () => {
    demoBackend()?.resetDemo()
    window.location.assign('/')
  }
  return (
    <div className="banner banner-demo" role="note">
      <FlaskConical aria-hidden />
      <span>Demo preview: simulated camera and sample data. No server or AI model is running, and nothing leaves this browser.</span>
      <button className="link-btn" onClick={reset}>Reset demo</button>
    </div>
  )
}
