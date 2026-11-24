import type { Theme } from './types'

const KEY = 'aq-theme'

export function storedTheme(): Theme {
  try {
    const t = localStorage.getItem(KEY)
    return t === 'light' || t === 'dark' ? t : 'system'
  } catch {
    return 'system'
  }
}

/** Apply a theme now and remember it on this device (also synced to the account by the caller). */
export function applyTheme(theme: Theme): void {
  const root = document.documentElement
  if (theme === 'system') root.removeAttribute('data-theme')
  else root.setAttribute('data-theme', theme)
  try {
    if (theme === 'system') localStorage.removeItem(KEY)
    else localStorage.setItem(KEY, theme)
  } catch { /* storage blocked: the choice lasts for this visit */ }
  const meta = document.querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]')
  const color = resolvedTheme() === 'light' ? '#f4f7fb' : '#0a101d'
  meta.forEach((m) => { if (theme !== 'system') m.content = color })
}

export function resolvedTheme(): 'light' | 'dark' {
  const attr = document.documentElement.getAttribute('data-theme')
  if (attr === 'light' || attr === 'dark') return attr
  return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
}
