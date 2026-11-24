import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource-variable/inter'
import '@fontsource-variable/jetbrains-mono'
import './styles/tokens.css'
import './styles/base.css'
import './styles/components.css'
import './styles/layout.css'
import './styles/pages.css'
import { App } from './App'
import { DEMO } from './lib/config'
import { setDemoBackend } from './demo/registry'

async function start() {
  // Demo builds only: the in-browser stand-in for the server (dropped from normal builds).
  if (DEMO) setDemoBackend(await import('./demo/backend'))
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
}
void start()
