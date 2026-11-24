import { ChartColumn, History, House, ScanLine, Settings, ShieldCheck, UserRound, type LucideIcon } from 'lucide-react'

export interface NavItem {
  to: string
  label: string
  icon: LucideIcon
  end?: boolean
  primary?: boolean
  adminOnly?: boolean
}

/** Bottom tab bar (mobile): Count sits in the middle, in the thumb's natural reach. */
export const TAB_ITEMS: NavItem[] = [
  { to: '/', label: 'Home', icon: House, end: true },
  { to: '/history', label: 'History', icon: History },
  { to: '/count', label: 'Count', icon: ScanLine, primary: true },
  { to: '/insights', label: 'Insights', icon: ChartColumn },
  { to: '/profile', label: 'Profile', icon: UserRound },
]

/** Sidebar (tablet & desktop). */
export const SIDEBAR_PRIMARY: NavItem[] = [
  { to: '/', label: 'Home', icon: House, end: true },
  { to: '/count', label: 'Live count', icon: ScanLine },
  { to: '/history', label: 'History', icon: History },
  { to: '/insights', label: 'Insights', icon: ChartColumn },
]

export const SIDEBAR_SECONDARY: NavItem[] = [
  { to: '/profile', label: 'Profile', icon: UserRound },
  { to: '/settings', label: 'Settings', icon: Settings },
  { to: '/admin', label: 'Admin', icon: ShieldCheck, adminOnly: true },
]
