import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { io, type Socket } from 'socket.io-client'
import { api, ApiError } from '../lib/api'
import { API_BASE } from '../lib/config'
import { formatNumber, normaliseCounts, EMPTY_COUNTS } from '../lib/format'
import { refreshSession } from '../lib/session'
import { accessTokenStale, getAccessToken } from '../lib/token'
import { uploadWithProgress, type UploadHandle } from '../lib/upload'
import type { BatchResultItem, Counts, JobInfo, RunKind, StationStatus } from '../lib/types'
import { useToast } from '../components/ui/feedback'
import { useAuth } from '../auth/AuthProvider'

export type Connection = 'connecting' | 'live' | 'reconnecting' | 'offline'

export interface RunSavedEvent {
  run_id: string
  kind?: RunKind
  status?: string
  counts: Partial<Counts>
  corrected_total?: number | null
  warning?: string
}

export interface BatchState {
  progress: { index: number; total: number; filename: string } | null
  results: { total_files: number; batch_totals: Counts; results: BatchResultItem[] } | null
}

interface LiveMetrics {
  counts: Counts
  activeTracks: number
  fps: number
  frameNumber: number
  sourceType: string
  isLive: boolean
  updatedAt: number
}

interface StationContextValue {
  connection: Connection
  isProcessing: boolean
  job: JobInfo | null
  metrics: LiveMetrics
  hasFrame: boolean
  lastRun: RunSavedEvent | null
  batch: BatchState
  subscribeFrame: (cb: (src: string | null) => void) => () => void
  startCamera: (cameraIndex: number) => Promise<void>
  uploadFile: (file: File, onProgress: (f: number) => void) => Promise<UploadHandle<unknown>>
  uploadBatch: (files: File[], onProgress: (f: number) => void) => Promise<UploadHandle<unknown>>
  processUrl: (url: string) => Promise<void>
  stop: () => Promise<void>
  reset: () => Promise<void>
  refreshStatus: () => Promise<void>
}

const StationContext = createContext<StationContextValue | null>(null)

const INITIAL_METRICS: LiveMetrics = { counts: EMPTY_COUNTS, activeTracks: 0, fps: 0, frameNumber: 0, sourceType: '', isLive: false, updatedAt: 0 }

export function StationProvider({ children }: { children: ReactNode }) {
  const toast = useToast()
  const navigate = useNavigate()
  const { user } = useAuth()
  // Read through a ref: the socket handlers are created once per sign-in.
  const hapticsRef = useRef(true)
  hapticsRef.current = user?.preferences.haptics !== false

  const [connection, setConnection] = useState<Connection>('connecting')
  const [isProcessing, setProcessing] = useState(false)
  const [job, setJob] = useState<JobInfo | null>(null)
  const [metrics, setMetrics] = useState<LiveMetrics>(INITIAL_METRICS)
  const [hasFrame, setHasFrame] = useState(false)
  const [lastRun, setLastRun] = useState<RunSavedEvent | null>(null)
  const [batch, setBatch] = useState<BatchState>({ progress: null, results: null })

  const frameRef = useRef<string | null>(null)
  const frameSubs = useRef(new Set<(src: string | null) => void>())
  const pending = useRef<Partial<LiveMetrics> | null>(null)
  const raf = useRef(0)
  const socketRef = useRef<Socket | null>(null)

  const pushFrame = useCallback((src: string | null) => {
    frameRef.current = src
    frameSubs.current.forEach((cb) => cb(src))
    setHasFrame(!!src)
  }, [])

  const subscribeFrame = useCallback((cb: (src: string | null) => void) => {
    frameSubs.current.add(cb)
    cb(frameRef.current)
    return () => { frameSubs.current.delete(cb) }
  }, [])

  const applyStatus = useCallback((s: StationStatus) => {
    setProcessing(!!s.is_processing)
    setJob(s.job ?? null)
    if (s.counts) {
      setMetrics((m) => ({ ...m, counts: normaliseCounts(s.counts), activeTracks: s.active_tracks ?? m.activeTracks,
        fps: s.fps ?? m.fps, frameNumber: s.frame_number ?? m.frameNumber, sourceType: s.source_type ?? m.sourceType, isLive: !!s.is_live }))
    }
  }, [])

  const refreshStatus = useCallback(async () => {
    const s = await api<StationStatus>('/api/status')
    applyStatus(s)
  }, [applyStatus])

  const buzz = useCallback((pattern: number | number[]) => {
    if (hapticsRef.current && 'vibrate' in navigator) { try { navigator.vibrate(pattern) } catch { /* unsupported */ } }
  }, [])

  // ── Socket lifecycle ─────────────────────────────────────────────────────
  useEffect(() => {
    const socket = io(API_BASE || undefined, {
      path: '/socket.io',
      transports: ['polling'], // works through every proxy (Render, Vercel, hatchery Wi-Fi)
      upgrade: false,
      autoConnect: false,
      reconnectionDelay: 1500,
      reconnectionDelayMax: 10_000,
      auth: (cb) => cb({ token: getAccessToken() }),
    })
    socketRef.current = socket
    let authRetries = 0

    const flush = () => {
      raf.current = 0
      const p = pending.current
      pending.current = null
      if (p) setMetrics((m) => ({ ...m, ...p, updatedAt: Date.now() }))
    }

    socket.on('connect', () => {
      authRetries = 0
      setConnection('live')
      refreshStatus().catch(() => {})
    })
    socket.on('disconnect', (reason) => setConnection(reason === 'io client disconnect' ? 'offline' : 'reconnecting'))
    socket.io.on('reconnect_attempt', () => setConnection('reconnecting'))
    socket.on('connect_error', async (err) => {
      if (err.message === 'unauthorized' && authRetries < 2) {
        authRetries += 1
        try { if (await refreshSession()) socket.connect() } catch { setConnection('reconnecting'); setTimeout(() => socket.connect(), 5000) }
        return
      }
      setConnection(navigator.onLine ? 'reconnecting' : 'offline')
    })

    socket.on('update', (d: { counts?: Partial<Counts>; active_tracks?: number; fps?: number; frame_number?: number; source_type?: string; is_live?: boolean }) => {
      pending.current = {
        counts: normaliseCounts(d.counts), activeTracks: d.active_tracks ?? 0, fps: d.fps ?? 0,
        frameNumber: d.frame_number ?? 0, sourceType: d.source_type ?? '', isLive: !!d.is_live,
      }
      if (!raf.current) raf.current = requestAnimationFrame(flush)
    })
    socket.on('frame', (d: { img: string }) => pushFrame(`data:image/jpeg;base64,${d.img}`))
    socket.on('image_result', (d: { annotated_image_b64?: string }) => { if (d.annotated_image_b64) pushFrame(`data:image/jpeg;base64,${d.annotated_image_b64}`) })

    socket.on('processing_started', (d: { source?: string; type?: string; started_by?: string }) => {
      setProcessing(true)
      setJob({ kind: d.type ?? '', label: d.source ?? '', started_at: new Date().toISOString(), started_by: d.started_by ?? null })
      if (d.type === 'batch_upload') setBatch({ progress: null, results: null })
    })
    socket.on('processing_completed', () => { setProcessing(false); setJob(null); setBatch((b) => ({ ...b, progress: null })) })
    socket.on('processing_stopped', () => { refreshStatus().catch(() => {}) })
    socket.on('processing_error', (d: { error?: string }) => {
      setProcessing(false)
      setJob(null)
      buzz([30, 60, 30])
      toast.show({ tone: 'error', title: 'Count stopped with an error', message: d.error || 'The source could not be processed.', id: 'station-error' })
    })
    socket.on('counts_reset', () => {
      setMetrics((m) => ({ ...m, counts: EMPTY_COUNTS, activeTracks: 0 }))
      pushFrame(null)
    })
    socket.on('batch_file_processing', (d: { filename: string; index: number; total: number }) => setBatch((b) => ({ ...b, progress: d })))
    socket.on('batch_results', (d: BatchState['results']) => setBatch({ progress: null, results: d && { ...d, batch_totals: normaliseCounts(d.batch_totals) } }))
    socket.on('run_saved', (d: RunSavedEvent) => {
      setLastRun(d)
      buzz(12)
      const total = normaliseCounts(d.counts).total
      toast.show({
        tone: d.warning ? 'warning' : 'success',
        title: d.kind === 'batch' ? 'Batch saved' : 'Count saved',
        message: `${formatNumber(total)} fish recorded${d.corrected_total != null ? ` (calibrated ${formatNumber(d.corrected_total)})` : ''}.`,
        action: { label: 'Open', onClick: () => navigate(`/history/${encodeURIComponent(d.run_id)}`) },
        id: 'run-saved',
      })
    })

    const goOffline = () => setConnection('offline')
    const goOnline = () => { if (!socket.connected) { setConnection('reconnecting'); socket.connect() } }
    window.addEventListener('offline', goOffline)
    window.addEventListener('online', goOnline)

    // Make sure the token is fresh before the first handshake.
    ;(accessTokenStale() ? refreshSession().catch(() => null) : Promise.resolve(null)).finally(() => socket.connect())

    return () => {
      window.removeEventListener('offline', goOffline)
      window.removeEventListener('online', goOnline)
      if (raf.current) cancelAnimationFrame(raf.current)
      socket.removeAllListeners()
      socket.io.removeAllListeners()
      socket.disconnect()
      socketRef.current = null
    }
  }, [])

  // ── Actions ──────────────────────────────────────────────────────────────
  const ensureFreshToken = useCallback(async () => {
    if (accessTokenStale(120_000)) {
      const p = await refreshSession()
      if (!p) throw new ApiError('Your session has ended. Please sign in again.', 401, 'session_expired')
    }
  }, [])

  const assertIdle = useCallback(async () => {
    const s = await api<StationStatus>('/api/status')
    applyStatus(s)
    if (s.is_processing) {
      const who = s.job?.started_by ? ` (started by ${s.job.started_by})` : ''
      throw new ApiError(`A count is already running${who}. Stop it before starting another.`, 409, 'busy')
    }
  }, [applyStatus])

  const value = useMemo<StationContextValue>(() => ({
    connection, isProcessing, job, metrics, hasFrame, lastRun, batch, subscribeFrame, refreshStatus,
    startCamera: async (cameraIndex) => {
      await api('/api/start_camera', { json: { camera_index: cameraIndex } })
    },
    processUrl: async (url) => {
      await api('/api/process_url', { json: { url } })
    },
    uploadFile: async (file, onProgress) => {
      await ensureFreshToken()
      await assertIdle() // do not push a 400 MB video only to be told the station is busy
      const form = new FormData()
      form.append('file', file)
      return uploadWithProgress('/api/upload', form, onProgress)
    },
    uploadBatch: async (files, onProgress) => {
      await ensureFreshToken()
      await assertIdle()
      const form = new FormData()
      files.forEach((f) => form.append('files', f))
      setBatch({ progress: null, results: null })
      return uploadWithProgress('/api/upload_batch', form, onProgress)
    },
    stop: async () => { await api('/api/stop', { method: 'POST' }) },
    reset: async () => { await api('/api/reset_counts', { method: 'POST' }) },
  }), [connection, isProcessing, job, metrics, hasFrame, lastRun, batch, subscribeFrame, refreshStatus, ensureFreshToken, assertIdle])

  return <StationContext.Provider value={value}>{children}</StationContext.Provider>
}

export function useStation(): StationContextValue {
  const ctx = useContext(StationContext)
  if (!ctx) throw new Error('useStation must be used inside <StationProvider>')
  return ctx
}
