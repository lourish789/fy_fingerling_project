import type { ClassKey, Counts, RunKind, RunStatus } from './types'

export const CLASS_KEYS: ClassKey[] = ['fingerling', 'post_fingerling', 'juvenile', 'unknown']
export const GRADED_CLASSES: Exclude<ClassKey, 'unknown'>[] = ['fingerling', 'post_fingerling', 'juvenile']

export const CLASS_LABEL: Record<ClassKey, string> = {
  fingerling: 'Fingerling',
  post_fingerling: 'Post-fingerling',
  juvenile: 'Juvenile',
  unknown: 'Unclassified',
}

export const EMPTY_COUNTS: Counts = { total: 0, fingerling: 0, post_fingerling: 0, juvenile: 0, unknown: 0 }

export function normaliseCounts(c?: Partial<Counts> | null): Counts {
  const out = { ...EMPTY_COUNTS }
  if (!c) return out
  for (const k of ['total', ...CLASS_KEYS] as const) out[k] = Number(c[k] ?? 0) || 0
  return out
}

const nf = new Intl.NumberFormat()
const compactNf = new Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 })

export function formatNumber(n: number | null | undefined, compact = false): string {
  if (n == null || !Number.isFinite(n)) return '—'
  if (compact && Math.abs(n) >= 10_000) return compactNf.format(n)
  return nf.format(n)
}

export function formatPercent(fraction: number, digits = 0): string {
  return `${(fraction * 100).toFixed(digits)}%`
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return '—'
  const s = Math.round(seconds)
  if (s < 60) return `${s} s`
  const m = Math.floor(s / 60)
  if (m < 60) return s % 60 ? `${m} min ${s % 60} s` : `${m} min`
  const h = Math.floor(m / 60)
  return `${h} h ${m % 60} min`
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB']
  let v = bytes / 1024
  let i = 0
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++ }
  return `${v.toFixed(v < 10 ? 1 : 0)} ${units[i]}`
}

export function parseDate(iso: string | null | undefined): Date | null {
  if (!iso) return null
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? null : d
}

const timeFmt = new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' })
const dateFmt = new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
const dayFmt = new Intl.DateTimeFormat(undefined, { weekday: 'long', day: 'numeric', month: 'short' })
const shortDayFmt = new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short' })

export function formatTime(iso: string | null | undefined): string {
  const d = parseDate(iso)
  return d ? timeFmt.format(d) : '—'
}

export function formatDate(iso: string | null | undefined): string {
  const d = parseDate(iso)
  return d ? dateFmt.format(d) : '—'
}

export function formatDateTime(iso: string | null | undefined): string {
  const d = parseDate(iso)
  return d ? `${dateFmt.format(d)}, ${timeFmt.format(d)}` : '—'
}

export function formatShortDay(isoDate: string): string {
  return shortDayFmt.format(new Date(`${isoDate}T12:00:00`))
}

function startOfDay(d: Date): number { return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime() }

/** "Today", "Yesterday", or "Monday 18 Nov" (local time). */
export function dayGroup(iso: string | null | undefined, now = new Date()): string {
  const d = parseDate(iso)
  if (!d) return 'Undated'
  const diff = Math.round((startOfDay(now) - startOfDay(d)) / 86_400_000)
  if (diff === 0) return 'Today'
  if (diff === 1) return 'Yesterday'
  return dayFmt.format(d)
}

/** "Today, 3:09 PM", "Yesterday, 8:39 AM", "20 Nov, 3:16 PM". */
export function formatDayTime(iso: string | null | undefined, now = new Date()): string {
  const d = parseDate(iso)
  if (!d) return '—'
  const g = dayGroup(iso, now)
  const day = g === 'Today' || g === 'Yesterday' ? g : shortDayFmt.format(d)
  return `${day}, ${timeFmt.format(d)}`
}

const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })
export function formatRelative(iso: string | null | undefined, now = Date.now()): string {
  const d = parseDate(iso)
  if (!d) return '—'
  const sec = Math.round((d.getTime() - now) / 1000)
  const abs = Math.abs(sec)
  if (abs < 45) return 'just now'
  if (abs < 3600) return rtf.format(Math.round(sec / 60), 'minute')
  if (abs < 86_400) return rtf.format(Math.round(sec / 3600), 'hour')
  if (abs < 7 * 86_400) return rtf.format(Math.round(sec / 86_400), 'day')
  return formatDate(iso)
}

export const RUN_KIND_LABEL: Record<RunKind, string> = {
  video: 'Video upload',
  camera: 'Live camera',
  url: 'Stream / URL',
  image: 'Single image',
  batch: 'Image batch',
}

export function statusTone(status: RunStatus): 'success' | 'warning' | 'danger' | 'neutral' {
  if (status === 'completed') return 'success'
  if (status === 'error') return 'danger'
  if (status === 'stopped' || status === 'reset' || status === 'superseded') return 'warning'
  return 'neutral'
}

export const STATUS_LABEL: Record<string, string> = {
  completed: 'Completed',
  stopped: 'Stopped early',
  error: 'Error',
  reset: 'Reset mid-run',
  superseded: 'Replaced',
}

export function initials(name: string | null | undefined, email?: string): string {
  const src = (name || email || '?').trim()
  const parts = src.split(/[\s@._-]+/).filter(Boolean)
  return ((parts[0]?.[0] ?? '?') + (parts.length > 1 ? parts[1][0] : '')).toUpperCase()
}

export function greeting(d = new Date()): string {
  const h = d.getHours()
  if (h < 12) return 'Good morning'
  if (h < 17) return 'Good afternoon'
  return 'Good evening'
}

/** Human device name from a user-agent string (sessions list). */
export function describeDevice(ua: string): { label: string; kind: 'phone' | 'tablet' | 'desktop' } {
  const s = ua || ''
  const kind = /iPad|Tablet/i.test(s) ? 'tablet' : /Mobi|iPhone|Android/i.test(s) ? 'phone' : 'desktop'
  const browser = /Edg\//.test(s) ? 'Edge' : /OPR\//.test(s) ? 'Opera' : /SamsungBrowser/.test(s) ? 'Samsung Internet'
    : /Chrome\//.test(s) ? 'Chrome' : /Firefox\//.test(s) ? 'Firefox' : /Safari\//.test(s) ? 'Safari' : 'Browser'
  const os = /Windows/.test(s) ? 'Windows' : /iPhone|iPad|iOS/.test(s) ? 'iOS' : /Android/.test(s) ? 'Android'
    : /Mac OS X|Macintosh/.test(s) ? 'macOS' : /Linux/.test(s) ? 'Linux' : ''
  return { label: os ? `${browser} on ${os}` : browser, kind }
}

/** Share of the classified total for each class (0..1). */
export function classShares(c: Counts): Record<ClassKey, number> {
  const sum = CLASS_KEYS.reduce((acc, k) => acc + c[k], 0)
  const out = {} as Record<ClassKey, number>
  CLASS_KEYS.forEach((k) => { out[k] = sum ? c[k] / sum : 0 })
  return out
}

/** Length-based strength (0–4) for the sign-up meter; mirrors the server's policy. */
export function passwordStrength(pw: string): number {
  if (!pw) return 0
  if (pw.length < 8 || new Set(pw).size < 4) return 1
  const variety = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter((r) => r.test(pw)).length
  if (pw.length >= 16 || (pw.length >= 12 && variety >= 3)) return 4
  if (pw.length >= 12 || variety >= 3) return 3
  return 2
}
