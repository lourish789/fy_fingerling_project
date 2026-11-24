/**
 * Demo mode only (VITE_DEMO=1): an in-browser stand-in for the AquaCount API and
 * counting station, so the interface can be explored with no server or database.
 * Responses mirror src/api and src/streaming/server.py. Nothing here runs a model.
 */
import type { AdminUser, Counts, Insights, Preferences, RunKind, RunRecord, User } from '../lib/types'
import { DEMO_EMAIL, DEMO_PASSWORD } from './registry'
import { LINE_Y, H, renderCrop, renderFrame, renderStill, resetFishIds, spawnFish, stillFish, type DemoFish } from './render'

/* ── Utilities ──────────────────────────────────────────────────────────── */
export function prng(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}
const iso = (d: Date) => d.toISOString().replace(/\.\d{3}Z$/, 'Z')
const zero = (): Counts => ({ total: 0, fingerling: 0, post_fingerling: 0, juvenile: 0, unknown: 0 })
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))
const json = (status: number, body: unknown, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json', ...headers } })
const err = (status: number, error: string, code: string, extra: Record<string, unknown> = {}) => json(status, { error, code, ...extra })

/* ── State (localStorage, so a reload keeps you signed in) ──────────────── */
interface DemoUser extends User { password: string | null }
interface DemoRun extends RunRecord { owner_id: string | null; seed: number; photos?: string[] }
interface State { users: DemoUser[]; session: string | null; runs: DemoRun[] }

const KEY = 'aq-demo-v1'
let state: State = load()

function load(): State {
  try {
    const raw = localStorage.getItem(KEY)
    if (raw) return JSON.parse(raw) as State
  } catch { /* storage blocked: start fresh */ }
  const s: State = { users: [], session: null, runs: [] }
  const ada = makeUser('demo-ada', DEMO_EMAIL, 'Ada Okafor', DEMO_PASSWORD, 'admin', 40)
  ada.onboarded = true
  ada.preferences = { hatchery_name: 'Lekki Fish Farm', role_title: 'Hatchery manager', setup_type: 'channel',
    size_focus: ['fingerling', 'post_fingerling', 'juvenile'], daily_target: 5000, default_source: 'camera', camera_index: 1 }
  const bo = makeUser('demo-bo', 'bo@aquacount.app', 'Bo Adeyemi', DEMO_PASSWORD, 'operator', 21)
  bo.onboarded = true
  s.users.push(ada, bo)
  s.runs.push(...seedRuns(ada, 1, 16), ...seedRuns(bo, 2, 5))
  return s
}
function save() { try { localStorage.setItem(KEY, JSON.stringify(state)) } catch { /* ignore */ } }
export function resetDemo() { try { localStorage.removeItem(KEY) } catch { /* ignore */ } state = load() }

function makeUser(id: string, email: string, name: string, password: string | null, role: 'admin' | 'operator', ageDays: number): DemoUser {
  const created = new Date(Date.now() - ageDays * 86_400_000)
  return { id, email, name, password, role, avatar_url: null, has_password: !!password, google_connected: false, google_email: null,
    onboarded: false, preferences: {}, created_at: iso(created), last_login_at: iso(new Date()) }
}
const publicUser = (u: DemoUser): User => { const { password: _p, ...rest } = u; return { ...rest, has_password: !!u.password } }

/** Realistic history: channel batches of a few hundred fish, the odd stopped run, photos. */
function seedRuns(owner: DemoUser, seed: number, n: number): DemoRun[] {
  const rand = prng(seed * 977)
  const runs: DemoRun[] = []
  for (let i = 0; i < n; i++) {
    const daysAgo = Math.floor(rand() * 13) + (i < 3 ? 0 : 1) * (i % 2)
    const start = new Date(Date.now() - daysAgo * 86_400_000)
    start.setHours(7 + Math.floor(rand() * 9), Math.floor(rand() * 60), 0, 0)
    if (start.getTime() > Date.now()) start.setTime(Date.now() - (i + 1) * 3_600_000)
    if (i < 2) start.setTime(Date.now() - (i + 1) * 95 * 60_000) // a couple from earlier today
    const r = rand()
    const kind: RunKind = r < 0.6 ? 'camera' : r < 0.78 ? 'video' : r < 0.9 ? 'batch' : 'image'
    const total = kind === 'camera' ? 160 + Math.floor(rand() * 180) : kind === 'video' ? 80 + Math.floor(rand() * 120)
      : kind === 'batch' ? 6 + Math.floor(rand() * 30) : 4 + Math.floor(rand() * 9)
    const status = kind !== 'image' && kind !== 'batch' && rand() < 0.12 ? 'stopped' : 'completed'
    const seconds = kind === 'camera' || kind === 'video' ? total * (2.2 + rand()) : 2 + rand() * 6
    const frames = kind === 'batch' ? Math.max(3, Math.round(total / 3)) : kind === 'image' ? 1 : Math.round(seconds * 4.6)
    runs.push(makeRun(owner, kind, splitCounts(total, rand), status, start, seconds, frames,
      kind === 'camera' ? `camera ${owner.preferences.camera_index ?? 1}` : kind === 'video' ? `channel_batch_${String(i + 1).padStart(2, '0')}.mp4`
        : kind === 'batch' ? `${frames} image(s)` : `IMG_2026${String(1100 + i)}.jpg`, seed * 100 + i))
  }
  return runs
}

function splitCounts(total: number, rand: () => number): Counts {
  const post = Math.round(total * (0.1 + rand() * 0.08))
  const juv = Math.round(total * (0.02 + rand() * 0.04))
  const unk = rand() < 0.4 ? Math.round(total * 0.01) : 0
  return { total, post_fingerling: post, juvenile: juv, unknown: unk, fingerling: Math.max(0, total - post - juv - unk) }
}

function makeRun(owner: DemoUser | null, kind: RunKind, counts: Counts, status: string, start: Date, seconds: number, frames: number, source: string, seed: number): DemoRun {
  const stamp = `${start.getFullYear()}${String(start.getMonth() + 1).padStart(2, '0')}${String(start.getDate()).padStart(2, '0')}_${String(start.getHours()).padStart(2, '0')}${String(start.getMinutes()).padStart(2, '0')}${String(start.getSeconds()).padStart(2, '0')}`
  const slug = source.replace(/\.[a-z0-9]+$/i, '').replace(/[^A-Za-z0-9_-]+/g, '-').slice(0, 30)
  return {
    run_id: `${stamp}_${kind === 'batch' ? 'batch' : slug}-${seed.toString(16).slice(-4)}`,
    kind, source, status, total: counts.total, counts, corrected_total: null, correction_factor: 1,
    warning: status === 'completed' ? '' : `Run ended as '${status}' before the end of the source. Counts cover only the part that was processed.`,
    frames_processed: frames, processing_seconds: Math.round(seconds * 10) / 10,
    started_at: iso(start), ended_at: iso(new Date(start.getTime() + seconds * 1000)), created_at: iso(start),
    owner: owner ? { id: owner.id, name: owner.name } : null, owner_id: owner?.id ?? null, seed,
  }
}

const currentUser = () => state.users.find((u) => u.id === state.session) ?? null
const payload = (u: DemoUser, extra: Record<string, unknown> = {}) =>
  ({ access_token: `demo.${u.id}.${Date.now()}`, token_type: 'Bearer', expires_in: 3600, user: publicUser(u), ...extra })

/* ── Station simulation ─────────────────────────────────────────────────── */
type Listener = (event: string, data: unknown) => void
const SETTINGS = {
  model_file: 'best.onnx', model_sha256_12: 'demo-preview', confidence_threshold: 0.5, nms_iou_threshold: 0.5,
  counting_mode: 'line_crossing', count_direction: 'down', counting_line_position: 0.5, counting_line_orientation: 'horizontal',
  min_hits: 3, max_distance_px: 160, max_age_frames: 30,
}

class Station {
  private subs = new Set<Listener>()
  processing = false
  job: { kind: string; label: string; started_at: string; started_by: string | null } | null = null
  counts = zero()
  private fish: DemoFish[] = []
  private timer = 0
  private frame = 0
  private t = 0
  private jobSeq = 0
  private recordStart = new Date()
  private owner: DemoUser | null = null
  private runKind: RunKind = 'camera'
  private limit = 0
  private rand = prng(Date.now() % 100000)
  isLive = false
  fps = 0

  subscribe(l: Listener) { this.subs.add(l); return () => { this.subs.delete(l) } }
  private emit(e: string, d: unknown) { this.subs.forEach((l) => l(e, d)) }

  status() {
    return { timestamp: iso(new Date()), frame_number: this.frame, counts: this.counts, current_detections: this.fish.length,
      active_tracks: this.fish.length, size_distribution: {}, fps: this.fps, source_type: this.isLive ? 'camera' : 'video',
      is_live: this.isLive, is_processing: this.processing, job: this.processing ? this.job : null }
  }

  private begin(kind: string, label: string, owner: DemoUser) {
    this.processing = true
    this.jobSeq += 1
    this.owner = owner
    this.job = { kind, label, started_at: iso(new Date()), started_by: owner.name }
    this.emit('processing_started', { source: label, type: kind, job: this.jobSeq, started_by: owner.name })
  }

  startStream(kind: 'camera' | 'url' | 'upload', label: string, owner: DemoUser) {
    this.begin(kind, label, owner)
    this.runKind = kind === 'upload' ? 'video' : kind
    this.isLive = kind !== 'upload'
    this.limit = kind === 'upload' ? 260 : 0 // a recorded clip ends by itself (~30 s)
    this.counts = zero()
    this.fish = []
    this.frame = 0
    this.recordStart = new Date()
    resetFishIds()
    this.timer = window.setInterval(() => this.tick(), 125)
  }

  private tick() {
    this.t += 1
    this.frame += 1
    this.fps = 7.6 + Math.sin(this.t / 9) * 0.6
    if (this.rand() < 0.16 && this.fish.length < 6) this.fish.push(spawnFish(this.rand))
    for (const f of this.fish) {
      const before = f.y
      f.y += f.speed
      f.x += Math.sin((this.t + f.wobble * 10) / 6) * 0.8
      if (before < LINE_Y && f.y >= LINE_Y) {
        this.counts[f.cls] += 1
        this.counts.total += 1
      }
    }
    this.fish = this.fish.filter((f) => f.y < H + 40)
    this.emit('update', this.status())
    this.emit('frame', { img: renderFrame(this.fish, this.counts, this.t) })
    if (this.limit && this.frame >= this.limit) this.finish('completed')
  }

  private saveRun(status: string) {
    if (!this.owner) return null
    const seconds = (Date.now() - this.recordStart.getTime()) / 1000
    const run = makeRun(this.owner, this.runKind, { ...this.counts }, status, this.recordStart, seconds, this.frame,
      this.job?.label ?? 'source', Math.floor(Math.random() * 1e6))
    state.runs.unshift(run)
    save()
    this.emit('run_saved', { run_id: run.run_id, kind: run.kind, status, counts: run.counts, corrected_total: null, correction_factor: 1, warning: run.warning, links: {} })
    return run
  }

  finish(status: 'completed' | 'stopped') {
    if (!this.processing) return
    clearInterval(this.timer)
    this.saveRun(status)
    this.processing = false
    this.job = null
    this.isLive = false
    this.fps = 0
    this.emit('processing_completed', { job: this.jobSeq })
  }

  stop() { this.finish('stopped'); this.emit('processing_stopped', {}) }

  reset() {
    if (this.processing) {
      this.saveRun('reset')
      this.recordStart = new Date()
      this.frame = 0
    }
    this.counts = zero()
    this.emit('counts_reset', {})
    this.emit('update', this.status())
  }

  async photo(name: string, owner: DemoUser) {
    this.begin('upload', name, owner)
    await sleep(900)
    const seed = Math.floor(Math.random() * 1e6)
    const rand = prng(seed)
    const fish = stillFish(4 + Math.floor(rand() * 8), rand)
    const counts = zero()
    fish.forEach((f) => { counts[f.cls] += 1; counts.total += 1 })
    const img = renderStill(fish, counts, seed)
    this.counts = counts
    this.emit('update', { ...this.status(), frame_number: 1, source_type: 'image' })
    this.emit('image_result', { annotated_image_b64: img.split(',')[1], counts })
    const run = makeRun(owner, 'image', counts, 'completed', new Date(), 0.9, 1, name, seed)
    state.runs.unshift(run)
    save()
    this.emit('run_saved', { run_id: run.run_id, kind: 'image', status: 'completed', counts, corrected_total: null, warning: '', links: {} })
    this.processing = false
    this.job = null
    this.emit('processing_completed', { job: this.jobSeq })
  }

  async batch(names: string[], owner: DemoUser) {
    this.begin('batch_upload', `${names.length} image(s)`, owner)
    const seed = Math.floor(Math.random() * 1e6)
    const totals = zero()
    const results = []
    for (let i = 0; i < names.length; i++) {
      this.emit('batch_file_processing', { filename: names[i], index: i + 1, total: names.length })
      await sleep(650)
      const rand = prng(seed + i)
      const fish = stillFish(1 + Math.floor(rand() * 6), rand)
      const c = zero()
      fish.forEach((f) => { c[f.cls] += 1; c.total += 1 })
      ;(Object.keys(totals) as (keyof Counts)[]).forEach((k) => { totals[k] += c[k] })
      results.push({ filename: names[i], status: 'success', counts: c, detections: c.total,
        label_summary: `Fingerling: ${c.fingerling}`, annotated_image: renderStill(fish, c, seed + i).split(',')[1] })
    }
    this.emit('batch_results', { total_files: names.length, batch_totals: totals, results })
    const run = makeRun(owner, 'batch', totals, 'completed', new Date(), names.length * 0.65, names.length, `${names.length} image(s)`, seed)
    run.photos = names
    state.runs.unshift(run)
    save()
    this.emit('run_saved', { run_id: run.run_id, kind: 'batch', status: 'completed', counts: totals, corrected_total: null, warning: '', links: {} })
    this.processing = false
    this.job = null
    this.emit('processing_completed', { job: this.jobSeq })
  }
}
export const station = new Station()

/* ── Socket stand-in (same events as Flask-SocketIO) ────────────────────── */
export function createDemoSocket() {
  const handlers = new Map<string, Set<(...a: unknown[]) => void>>()
  const fire = (e: string, ...a: unknown[]) => handlers.get(e)?.forEach((h) => h(...a))
  let off: (() => void) | null = null
  const sock = {
    connected: false,
    io: { on: () => sock.io, removeAllListeners: () => sock.io },
    on(e: string, h: (...a: unknown[]) => void) { if (!handlers.has(e)) handlers.set(e, new Set()); handlers.get(e)!.add(h); return sock },
    removeAllListeners() { handlers.clear(); return sock },
    connect() {
      setTimeout(() => {
        sock.connected = true
        off = station.subscribe((e, d) => fire(e, d))
        fire('connect')
      }, 350)
      return sock
    },
    disconnect() { off?.(); off = null; sock.connected = false; fire('disconnect', 'io client disconnect'); return sock },
  }
  return sock
}

/* ── API stand-in ───────────────────────────────────────────────────────── */
function needUser(): DemoUser | Response {
  const u = currentUser()
  return u ?? err(401, 'Sign in to continue.', 'unauthorized')
}

function visibleRuns(u: DemoUser, all: boolean) {
  return state.runs.filter((r) => (all && u.role === 'admin') || r.owner_id === u.id)
}

function insights(u: DemoUser, q: URLSearchParams): Insights {
  const days = Math.max(1, Math.min(366, Number(q.get('days') || 14)))
  const all = q.get('scope') === 'all' && u.role === 'admin'
  const runs = visibleRuns(u, all)
  const today = new Date(); today.setHours(0, 0, 0, 0)
  const first = new Date(today.getTime() - (days - 1) * 86_400_000)
  const key = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  const series = Array.from({ length: days }, (_, i) => ({ date: key(new Date(first.getTime() + i * 86_400_000)), fish: 0, runs: 0 }))
  const byDate = new Map(series.map((s) => [s.date, s]))
  const classes = { fingerling: 0, post_fingerling: 0, juvenile: 0, unknown: 0 }
  const statuses: Record<string, number> = {}
  const kinds: Record<string, number> = {}
  const hours: Record<number, number> = {}
  const fps: number[] = []
  const inPeriod = runs.filter((r) => new Date(r.started_at!) >= first)
  for (const r of inPeriod) {
    const d = new Date(r.started_at!)
    const b = byDate.get(key(d))
    if (b) { b.fish += r.total; b.runs += 1 }
    hours[d.getHours()] = (hours[d.getHours()] ?? 0) + r.total
    statuses[r.status] = (statuses[r.status] ?? 0) + 1
    kinds[r.kind] = (kinds[r.kind] ?? 0) + 1
    ;(Object.keys(classes) as (keyof typeof classes)[]).forEach((k) => { classes[k] += r.counts[k] ?? 0 })
    if ((r.kind === 'camera' || r.kind === 'video' || r.kind === 'url') && r.processing_seconds > 0) fps.push(r.frames_processed / r.processing_seconds)
  }
  const fish = inPeriod.reduce((a, r) => a + r.total, 0)
  const best = series.reduce((a, s) => (s.fish > (a?.fish ?? 0) ? s : a), null as (typeof series)[number] | null)
  const busiest = Object.entries(hours).sort((a, b) => b[1] - a[1])[0]
  const t = byDate.get(key(today)) ?? { fish: 0, runs: 0 }
  return {
    scope: all ? 'all' : 'mine', days, today: { fish: t.fish, runs: t.runs },
    period: { fish, runs: inPeriod.length, avg_fish_per_run: inPeriod.length ? Math.round((fish / inPeriod.length) * 10) / 10 : 0,
      best_day: best, avg_processing_fps: fps.length ? Math.round((fps.reduce((a, b) => a + b, 0) / fps.length) * 100) / 100 : null,
      completed_share: inPeriod.length ? (statuses.completed ?? 0) / inPeriod.length : null },
    lifetime: { runs: runs.length, fish: runs.reduce((a, r) => a + r.total, 0) },
    series, classes, statuses, kinds, busiest_hour: busiest ? Number(busiest[0]) : null,
  }
}

function runDetail(r: DemoRun) {
  const camera = r.kind === 'camera' || r.kind === 'video' || r.kind === 'url'
  const files = camera
    ? [{ name: 'report.html', label: 'Printable report', bytes: 4800 }, { name: 'events.csv', label: 'Fish log (CSV)', bytes: 120 * r.total }, { name: 'summary.json', label: 'Summary (JSON)', bytes: 1900 }]
    : r.kind === 'batch'
      ? [{ name: 'batch_summary.csv', label: 'Batch summary (CSV)', bytes: 90 * r.frames_processed }, { name: 'summary.json', label: 'Summary (JSON)', bytes: 2400 }]
      : [{ name: 'annotated.jpg', label: 'Annotated image', bytes: 84_000 }, { name: 'summary.json', label: 'Summary (JSON)', bytes: 900 }]
  const crops: { path: string; seq: number; class: string }[] = []
  if (camera) {
    const order: string[] = []
    ;(['fingerling', 'post_fingerling', 'juvenile', 'unknown'] as const).forEach((k) => { for (let i = 0; i < (r.counts[k] ?? 0); i++) order.push(k) })
    const rand = prng(r.seed)
    for (let i = order.length - 1; i > 0; i--) { const j = Math.floor(rand() * (i + 1)); [order[i], order[j]] = [order[j], order[i]] }
    order.forEach((c, i) => { if (i >= order.length - 120) crops.push({ path: `crops/${String(i + 1).padStart(6, '0')}_${c}.jpg`, seq: i + 1, class: c }) })
  }
  const nPhotos = r.kind === 'batch' ? r.frames_processed : 0
  const results = Array.from({ length: nPhotos }, (_, i) => {
    const rand = prng(r.seed + i)
    const fish = stillFish(1 + Math.floor(rand() * 6), rand)
    return { filename: r.photos?.[i] ?? `IMG_${20261100 + i}.jpg`, status: 'success' as const, counts: { ...zero(), total: fish.length, fingerling: fish.length },
      detections: fish.length, label_summary: `Fingerling: ${fish.length}`, image: `images/${String(i + 1).padStart(3, '0')}_photo.jpg` }
  })
  return {
    run: r, files_available: true, files, crops, crops_total: r.total && camera ? r.total : 0,
    images: results.map((x) => x.image),
    summary: { settings: SETTINGS, correction_note: 'Uncalibrated: no hand-count batches recorded yet.', results },
    media_token: 'demo', media_expires_in: 900,
  }
}

const media = new Map<string, string>()
/** Run files in demo mode: generated images, and Blob URLs for reports and logs. */
export function demoFileUrl(runId: string, path: string): string {
  const k = `${runId}/${path}`
  if (media.has(k)) return media.get(k)!
  const r = state.runs.find((x) => x.run_id === runId)
  if (!r) return ''
  let url = ''
  const crop = path.match(/^crops\/(\d+)_([a-z_]+)\.jpg$/)
  const photo = path.match(/^images\/(\d+)_/)
  if (crop) url = renderCrop((crop[2] === 'unknown' ? 'fingerling' : crop[2]) as DemoFish['cls'], Number(crop[1]))
  else if (photo || path === 'annotated.jpg') {
    const i = photo ? Number(photo[1]) - 1 : 0
    const rand = prng(r.seed + i)
    const fish = stillFish(path === 'annotated.jpg' ? r.total : 1 + Math.floor(rand() * 6), rand)
    const c = zero(); fish.forEach((f) => { c[f.cls] += 1; c.total += 1 })
    url = renderStill(fish, c, r.seed + i)
  } else {
    const blob = (body: string, type: string) => URL.createObjectURL(new Blob([body], { type }))
    if (path === 'summary.json') url = blob(JSON.stringify({ ...r, settings: SETTINGS }, null, 2), 'application/json')
    else if (path.endsWith('.csv')) {
      const rows = ['seq,wall_time,class,mean_confidence,direction']
      for (let i = 1; i <= Math.min(r.total, 500); i++) rows.push(`${i},${r.started_at},fingerling,0.8${i % 10},down`)
      url = blob(rows.join('\n'), 'text/csv')
    } else if (path === 'report.html') {
      url = blob(`<!doctype html><meta charset="utf-8"><title>AquaCount report ${r.run_id}</title><body style="font:15px system-ui;max-width:720px;margin:24px auto;padding:0 16px">
<h1>AquaCount: batch count report</h1><p style="color:#666">Run ${r.run_id} · source ${r.source} · status ${r.status} · DEMO DATA</p>
<table style="width:100%;border-collapse:collapse">${Object.entries(r.counts).map(([k, v]) => `<tr><td style="border-bottom:1px solid #ddd;padding:6px">${k}</td><td style="text-align:right;border-bottom:1px solid #ddd;padding:6px"><b>${v}</b></td></tr>`).join('')}</table>
<p style="color:#666">Machine counts are estimates. Check them against a hand count before relying on them for a sale.</p></body>`, 'text/html')
    }
  }
  media.set(k, url)
  return url
}

export async function demoFetch(input: string, init: RequestInit = {}): Promise<Response> {
  await sleep(120 + Math.random() * 220) // feel like a network, and show the loading states
  const url = new URL(input, 'http://demo.local')
  const path = url.pathname
  const method = (init.method || 'GET').toUpperCase()
  let body: Record<string, unknown> = {}
  if (typeof init.body === 'string') { try { body = JSON.parse(init.body) } catch { /* not JSON */ } }

  // ── Public auth ──
  if (path === '/api/health') return json(200, { status: 'ok', version: '2.0.0', model_loaded: true })
  if (path === '/api/auth/config') return json(200, { google_client_id: null, signup_enabled: true, password_reset: 'console', version: '2.0.0' })
  if (path === '/api/auth/refresh') {
    const u = currentUser()
    return u ? json(200, payload(u)) : err(401, 'You are signed out.', 'no_session')
  }
  if (path === '/api/auth/login' && method === 'POST') {
    const email = String(body.email || '').trim().toLowerCase()
    const u = state.users.find((x) => x.email === email)
    if (!u || u.password !== body.password) return err(401, 'Incorrect email or password. In the demo, try demo@aquacount.app / fingerlings.', 'invalid_credentials')
    state.session = u.id; u.last_login_at = iso(new Date()); save()
    return json(200, payload(u))
  }
  if (path === '/api/auth/signup' && method === 'POST') {
    const email = String(body.email || '').trim().toLowerCase()
    const name = String(body.name || '').trim()
    if (!name) return err(400, 'Enter your name.', 'invalid_name', { field: 'name' })
    if (!/^\S+@\S+\.\S+$/.test(email)) return err(400, 'Enter a valid email address.', 'invalid_email', { field: 'email' })
    if (String(body.password || '').length < 8) return err(400, 'Use at least 8 characters.', 'weak_password', { field: 'password' })
    if (state.users.some((x) => x.email === email)) return err(409, 'An account with this email already exists. Sign in instead.', 'email_taken', { field: 'email' })
    // In the demo every new account is an administrator, so every screen can be explored.
    const u = makeUser(`demo-${Date.now().toString(36)}`, email, name, String(body.password), 'admin', 0)
    state.users.push(u)
    state.runs.push(...seedRuns(u, Date.now() % 997, 12))
    state.session = u.id
    save()
    return json(201, payload(u, { is_new: true }))
  }
  if (path === '/api/auth/logout' || path === '/api/auth/logout-all') { state.session = null; save(); return json(200, { ok: true }) }
  if (path === '/api/auth/forgot') return json(202, { ok: true, delivery: 'console', message: 'If an account exists for that email, a reset link is on its way.' })
  if (path === '/api/auth/reset') return err(400, 'Password reset links are not available in the demo.', 'invalid_token')
  if (path.startsWith('/api/auth/google')) return err(400, 'Google sign-in is switched on with GOOGLE_CLIENT_ID on the server. It is not available in the demo.', 'google_disabled')

  const u = needUser()
  if (u instanceof Response) return u

  // ── Me ──
  if (path === '/api/me' && method === 'GET') {
    const mine = state.runs.filter((r) => r.owner_id === u.id)
    return json(200, { user: publicUser(u), stats: { runs: mine.length, fish_counted: mine.reduce((a, r) => a + r.total, 0) } })
  }
  if (path === '/api/me' && method === 'PATCH') { if (body.name) u.name = String(body.name); save(); return json(200, { user: publicUser(u) }) }
  if (path === '/api/me' && method === 'DELETE') return err(400, 'Deleting accounts is turned off in the demo.', 'demo')
  if (path === '/api/me/preferences') { u.preferences = { ...u.preferences, ...(body as Preferences) }; save(); return json(200, { user: publicUser(u) }) }
  if (path === '/api/me/onboarding') {
    const { name, ...prefs } = body
    if (typeof name === 'string' && name.trim()) u.name = name.trim()
    u.preferences = { ...u.preferences, ...(prefs as Preferences) }
    u.onboarded = true
    save()
    return json(200, { user: publicUser(u) })
  }
  if (path === '/api/me/password') {
    if (u.password && body.current_password !== u.password) return err(400, 'Your current password is incorrect.', 'invalid_credentials', { field: 'current_password' })
    if (String(body.new_password || '').length < 8) return err(400, 'Use at least 8 characters.', 'weak_password', { field: 'new_password' })
    u.password = String(body.new_password); save()
    return json(200, { user: publicUser(u), message: 'Password changed. Other devices have been signed out.' })
  }
  if (path === '/api/me/sessions') {
    const now = Date.now()
    return json(200, { sessions: [
      { id: 'this', user_agent: navigator.userAgent, ip: '192.168.1.23', signed_in_at: iso(new Date(now - 3_600_000)), last_active_at: iso(new Date(now)), expires_at: null, current: true },
      { id: 'phone', user_agent: 'Mozilla/5.0 (Linux; Android 14) AppleWebKit Chrome/130 Mobile Safari/537.36', ip: '192.168.1.41', signed_in_at: iso(new Date(now - 6 * 86_400_000)), last_active_at: iso(new Date(now - 2 * 3_600_000)), expires_at: null, current: false },
    ] })
  }
  if (path.startsWith('/api/me/sessions/')) return json(200, { ok: true, current: false })

  // ── Runs & insights ──
  if (path === '/api/runs') {
    const all = url.searchParams.get('scope') === 'all' && u.role === 'admin'
    const status = url.searchParams.get('status')
    const q = (url.searchParams.get('q') || '').toLowerCase()
    const limit = Number(url.searchParams.get('limit') || 30)
    const offset = Number(url.searchParams.get('offset') || 0)
    const list = visibleRuns(u, all)
      .filter((r) => !status || r.status === status)
      .filter((r) => !q || r.run_id.toLowerCase().includes(q) || r.source.toLowerCase().includes(q))
      .sort((a, b) => (b.started_at ?? '').localeCompare(a.started_at ?? ''))
    return json(200, { runs: list.slice(offset, offset + limit), total: list.length, limit, offset, has_more: offset + limit < list.length, scope: all ? 'all' : 'mine' })
  }
  const runMatch = path.match(/^\/api\/runs\/([^/]+)$/)
  if (runMatch) {
    const r = state.runs.find((x) => x.run_id === decodeURIComponent(runMatch[1]))
    if (!r || (u.role !== 'admin' && r.owner_id !== u.id)) return err(404, 'Run not found.', 'not_found')
    return json(200, runDetail(r))
  }
  if (path === '/api/insights') return json(200, insights(u, url.searchParams))

  // ── Admin ──
  if (path === '/api/admin/users' && u.role === 'admin') {
    const users: AdminUser[] = state.users.map((x) => ({ id: x.id, email: x.email, name: x.name, avatar_url: null, role: x.role, is_active: true,
      google_connected: false, has_password: !!x.password, runs: state.runs.filter((r) => r.owner_id === x.id).length,
      created_at: x.created_at, last_login_at: x.last_login_at, is_you: x.id === u.id }))
    return json(200, { users })
  }
  const adminUser = path.match(/^\/api\/admin\/users\/(.+)$/)
  if (adminUser && u.role === 'admin') {
    const target = state.users.find((x) => x.id === decodeURIComponent(adminUser[1]))
    if (!target) return err(404, 'User not found.', 'not_found')
    if (body.role && target.id === u.id && body.role !== 'admin') return err(400, 'The station needs at least one active administrator.', 'last_admin')
    if (body.role === 'admin' || body.role === 'operator') target.role = body.role
    save()
    return json(200, { user: { id: target.id, role: target.role, is_active: body.is_active ?? true } })
  }
  if (path === '/api/admin/station' && u.role === 'admin') {
    return json(200, { version: '2.0.0 (demo)', model_loaded: true, settings: SETTINGS, calibration: { factor: 1, note: 'Uncalibrated' },
      is_processing: station.processing, runs_dir: 'output/runs', database: 'demo (in this browser)', users: state.users.length,
      runs_recorded: state.runs.length, features: { google_sign_in: false, email: false, open_signup: true } })
  }
  if (path.startsWith('/api/admin/')) return err(403, 'You do not have permission to do that.', 'forbidden')

  // ── Station ──
  if (path === '/api/status') return json(200, station.status())
  const busy = () => err(409, 'A count is already running. Stop it before starting another.', 'busy', { busy: true })
  if (path === '/api/start_camera') {
    if (station.processing) return busy()
    station.startStream('camera', `camera ${Number(body.camera_index ?? 0)}`, u)
    return json(200, { success: true })
  }
  if (path === '/api/process_url') {
    if (station.processing) return busy()
    station.startStream('url', String(body.url || 'stream'), u)
    return json(200, { success: true })
  }
  if (path === '/api/upload') {
    if (station.processing) return busy()
    const file = init.body instanceof FormData ? (init.body.get('file') as File | null) : null
    const name = file?.name || 'upload.mp4'
    if (file && file.type.startsWith('image/')) void station.photo(name, u)
    else station.startStream('upload', name, u)
    return json(200, { success: true, filename: name })
  }
  if (path === '/api/upload_batch') {
    if (station.processing) return busy()
    const files = init.body instanceof FormData ? (init.body.getAll('files') as File[]) : []
    void station.batch(files.map((f) => f.name), u)
    return json(200, { success: true, count: files.length })
  }
  if (path === '/api/stop') { station.stop(); return json(200, { success: true, message: 'Stop requested.' }) }
  if (path === '/api/reset_counts') { station.reset(); return json(200, { success: true }) }

  return err(404, 'Not found.', 'not_found')
}
