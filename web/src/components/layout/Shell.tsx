import { Suspense, useCallback, useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { ChevronLeft, LogOut, Moon, Settings, ShieldCheck, Sun, UserRound, WifiOff, X, BookOpen } from 'lucide-react'
import { useRegisterSW } from 'virtual:pwa-register/react'
import { useAuth, useUser } from '../../auth/AuthProvider'
import { StationProvider, useStation, type Connection } from '../../station/StationProvider'
import { applyTheme, resolvedTheme } from '../../lib/theme'
import { APP_VERSION } from '../../lib/config'
import { api } from '../../lib/api'
import type { User } from '../../lib/types'
import { BrandLockup, BrandMark } from '../BrandMark'
import { Avatar, cx, Spinner } from '../ui/primitives'
import { useToast } from '../ui/feedback'
import { PageMetaContext, type PageMeta } from './pageMeta'
import { SIDEBAR_PRIMARY, SIDEBAR_SECONDARY, TAB_ITEMS } from './navigation'
import { useOnline } from '../../hooks/useOnline'

/* ── Connection chip ────────────────────────────────────────────────────── */
const CONN_LABEL: Record<Connection, string> = { connecting: 'Connecting', live: 'Live', reconnecting: 'Reconnecting', offline: 'Offline' }

export function ConnectionChip() {
  const { connection, isProcessing } = useStation()
  const counting = isProcessing && connection === 'live'
  const label = counting ? 'Counting' : CONN_LABEL[connection]
  return (
    <span className={cx('conn', counting ? 'conn-counting' : `conn-${connection}`)} role="status" aria-label={`Station: ${label}`} title={`Counting station: ${label}`}>
      <span className="dot" aria-hidden /><span className="conn-label">{label}</span>
    </span>
  )
}

/* ── Top bar ────────────────────────────────────────────────────────────── */
function TopBar({ meta, onOpenDrawer }: { meta: PageMeta; onOpenDrawer: () => void }) {
  const user = useUser()
  const navigate = useNavigate()
  const [scrolled, setScrolled] = useState(false)
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 4)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <header className={cx('topbar', scrolled && 'is-scrolled')}>
      {meta.back ? (
        <button className="icon-btn topbar-back" onClick={() => (window.history.length > 1 ? navigate(-1) : navigate(meta.back!))} aria-label="Back">
          <ChevronLeft />
        </button>
      ) : (
        <Link to="/" className="brand-mini" aria-label="AquaCount home"><BrandMark className="brand-mark" /></Link>
      )}
      <div className="topbar-titles">
        <h1 className="topbar-title">{meta.title}</h1>
        {meta.subtitle && <div className="topbar-subtitle">{meta.subtitle}</div>}
      </div>
      <div className="topbar-actions">
        {meta.actions}
        <ConnectionChip />
        <button className="avatar-btn" onClick={onOpenDrawer} aria-label="Open account menu" aria-haspopup="dialog">
          <Avatar name={user.name} email={user.email} src={user.avatar_url} size="sm" />
        </button>
      </div>
    </header>
  )
}

/* ── Bottom tab bar (mobile) ────────────────────────────────────────────── */
function BottomNav() {
  const { isProcessing } = useStation()
  return (
    <nav className="bottomnav" aria-label="Primary">
      {TAB_ITEMS.map(({ to, label, icon: Icon, end, primary }) => (
        <NavLink key={to} to={to} end={end}
          className={({ isActive }) => cx('tab', isActive && 'active', primary && 'tab-primary', primary && isProcessing && 'is-counting')}
          aria-label={primary && isProcessing ? 'Count (counting now)' : label}>
          {primary ? <span className="tab-fab"><Icon /></span> : <Icon />}
          <span>{label}</span>
        </NavLink>
      ))}
    </nav>
  )
}

/* ── Sidebar (≥ 768px) ──────────────────────────────────────────────────── */
function Sidebar({ onOpenDrawer }: { onOpenDrawer: () => void }) {
  const user = useUser()
  const { isProcessing } = useStation()
  const link = ({ isActive }: { isActive: boolean }) => cx('side-link', isActive && 'active')
  return (
    <aside className="sidebar" aria-label="Main navigation">
      <Link to="/" className="sidebar-brand" aria-label="AquaCount home"><BrandLockup /></Link>
      <nav className="sidebar-nav">
        {SIDEBAR_PRIMARY.map(({ to, label, icon: Icon, end }) => (
          <NavLink key={to} to={to} end={end} className={(s) => cx(link(s), to === '/count' && isProcessing && 'is-counting')} title={label}>
            <Icon aria-hidden /><span className="side-label">{label}</span>
          </NavLink>
        ))}
      </nav>
      <nav className="sidebar-section" aria-label="Account">
        {SIDEBAR_SECONDARY.filter((i) => !i.adminOnly || user.role === 'admin').map(({ to, label, icon: Icon }) => (
          <NavLink key={to} to={to} className={link} title={label}><Icon aria-hidden /><span className="side-label">{label}</span></NavLink>
        ))}
      </nav>
      <div className="sidebar-foot">
        <ConnectionChip />
        <button className="sidebar-user" onClick={onOpenDrawer} aria-label="Open account menu">
          <Avatar name={user.name} email={user.email} src={user.avatar_url} />
          <span className="user-meta">
            <span className="truncate" style={{ fontWeight: 600 }}>{user.name || user.email}</span>
            <span className="truncate xsmall muted">{user.preferences.hatchery_name || user.email}</span>
          </span>
        </button>
      </div>
    </aside>
  )
}

/* ── Profile drawer ─────────────────────────────────────────────────────── */
function ProfileDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const user = useUser()
  const { logout, setUser } = useAuth()
  const [busy, setBusy] = useState(false)
  const [theme, setTheme] = useState<'light' | 'dark'>(() => resolvedTheme())

  useEffect(() => {
    if (!open) return
    setTheme(resolvedTheme())
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => { document.removeEventListener('keydown', onKey); document.body.style.overflow = '' }
  }, [open, onClose])

  if (!open) return null
  const toggleTheme = () => {
    const next = theme === 'dark' ? 'light' : 'dark'
    applyTheme(next)
    setTheme(next)
    // The theme belongs to the account (it follows the user to other devices).
    api<{ user: User }>('/api/me/preferences', { method: 'PATCH', json: { theme: next } }).then((r) => setUser(r.user)).catch(() => {})
  }
  const go = (cb?: () => void) => () => { onClose(); cb?.() }

  return (
    <>
      <div className="scrim" onClick={onClose} />
      <div className="drawer" role="dialog" aria-modal="true" aria-label="Account menu">
        <div className="drawer-head">
          <span className="caps muted">Account</span>
          <button className="icon-btn" onClick={onClose} aria-label="Close menu" autoFocus><X /></button>
        </div>
        <div className="drawer-user">
          <Avatar name={user.name} email={user.email} src={user.avatar_url} size="lg" />
          <div className="grow">
            <div className="truncate" style={{ fontWeight: 650, fontSize: 17 }}>{user.name || 'Unnamed'}</div>
            <div className="truncate small muted">{user.email}</div>
            <div className="xsmall" style={{ marginTop: 4, color: 'var(--accent)', fontWeight: 600 }}>{user.role === 'admin' ? 'Station administrator' : 'Operator'}</div>
          </div>
        </div>
        <nav className="drawer-nav">
          <Link to="/profile" className="drawer-link" onClick={go()}><UserRound />Profile &amp; security</Link>
          <Link to="/settings" className="drawer-link" onClick={go()}><Settings />Settings</Link>
          {user.role === 'admin' && <Link to="/admin" className="drawer-link" onClick={go()}><ShieldCheck />Admin &amp; station</Link>}
          <Link to="/settings#guide" className="drawer-link" onClick={go()}><BookOpen />Counting guide</Link>
          <button className="drawer-link" onClick={toggleTheme} aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}>
            {theme === 'dark' ? <Sun /> : <Moon />}{theme === 'dark' ? 'Light theme' : 'Dark theme'}
          </button>
          <hr style={{ margin: '8px 0' }} />
          <button className="drawer-link danger" disabled={busy} onClick={async () => { setBusy(true); await logout(); onClose() }}>
            {busy ? <Spinner /> : <LogOut />}Sign out
          </button>
        </nav>
        <div className="drawer-foot">AquaCount {APP_VERSION}</div>
      </div>
    </>
  )
}

/* ── Banners: offline, service-worker update ────────────────────────────── */
function OfflineBanner() {
  const online = useOnline()
  if (online) return null
  return <div className="banner" role="status"><WifiOff aria-hidden />You are offline. Live counts resume when the connection returns.</div>
}

function UpdatePrompt() {
  const toast = useToast()
  const { needRefresh: [needRefresh], updateServiceWorker } = useRegisterSW({
    onRegisteredSW(_url, reg) {
      if (reg) setInterval(() => { reg.update().catch(() => {}) }, 60 * 60 * 1000)
    },
  })
  useEffect(() => {
    if (!needRefresh) return
    toast.show({
      id: 'sw-update', tone: 'info', duration: 0, title: 'Update ready',
      message: 'A new version of AquaCount is available.',
      action: { label: 'Reload', onClick: () => updateServiceWorker(true) },
    })
  }, [needRefresh, toast, updateServiceWorker])
  return null
}

/* ── App shell ──────────────────────────────────────────────────────────── */
export function AppShell() {
  const [meta, setMeta] = useState<PageMeta>({ title: 'AquaCount' })
  const [drawer, setDrawer] = useState(false)
  const location = useLocation()
  const openDrawer = useCallback(() => setDrawer(true), [])
  const closeDrawer = useCallback(() => setDrawer(false), [])

  useEffect(() => { window.scrollTo({ top: 0 }) }, [location.pathname])

  return (
    <StationProvider>
      <PageMetaContext.Provider value={setMeta}>
        <a href="#main" className="skip-link">Skip to content</a>
        <div className="shell">
          <Sidebar onOpenDrawer={openDrawer} />
          <div className="shell-main">
            <OfflineBanner />
            <TopBar meta={meta} onOpenDrawer={openDrawer} />
            <main id="main" tabIndex={-1}>
              <Suspense fallback={<div className="page" aria-busy="true"><div className="state"><Spinner label="Loading" /></div></div>}>
                <Outlet />
              </Suspense>
            </main>
          </div>
        </div>
        <BottomNav />
        <ProfileDrawer open={drawer} onClose={closeDrawer} />
        <UpdatePrompt />
      </PageMetaContext.Provider>
    </StationProvider>
  )
}
