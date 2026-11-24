import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent, type DragEvent, type FormEvent, type ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  Camera, CircleAlert, CircleCheck, FileVideo, Image as ImageIcon, Images, Link2, Maximize2, Minus, Play, Plus,
  RotateCcw, ScanLine, Square, TriangleAlert, Upload, Video, X,
} from 'lucide-react'
import { useAuth, useUser } from '../auth/AuthProvider'
import { useStation } from '../station/StationProvider'
import { usePageMeta } from '../components/layout/pageMeta'
import { Badge, Button, Callout, Card, ProgressBar, Segmented, Spinner, TextField, cx } from '../components/ui/primitives'
import { ConfirmDialog, useToast } from '../components/ui/feedback'
import { ClassBar, ClassTiles, LiveNumber } from '../components/counts'
import { api, ApiError, errorMessage } from '../lib/api'
import { CLASS_KEYS, CLASS_LABEL, formatBytes, formatNumber, normaliseCounts } from '../lib/format'
import type { SourceKind, User } from '../lib/types'

const SOURCES: { value: SourceKind; label: string; icon: ReactNode }[] = [
  { value: 'camera', label: 'Camera', icon: <Camera aria-hidden /> },
  { value: 'upload', label: 'Upload', icon: <Upload aria-hidden /> },
  { value: 'batch', label: 'Batch', icon: <Images aria-hidden /> },
  { value: 'url', label: 'Stream', icon: <Link2 aria-hidden /> },
]

/* ── Live feed ──────────────────────────────────────────────────────────── */
function LiveFeed() {
  const { subscribeFrame, hasFrame, isProcessing, metrics, connection } = useStation()
  const imgRef = useRef<HTMLImageElement>(null)
  const boxRef = useRef<HTMLDivElement>(null)

  // Frames are written straight to the <img>, so the page does not re-render 8 times a second.
  useEffect(() => subscribeFrame((src) => {
    const img = imgRef.current
    if (!img) return
    if (src) img.src = src
    else img.removeAttribute('src')
  }), [subscribeFrame])

  const fullscreen = () => {
    const el = boxRef.current
    if (!el) return
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {})
    else el.requestFullscreen?.().catch(() => {})
  }

  return (
    <div className="card card-flush">
      <div className="feed" ref={boxRef}>
        <img ref={imgRef} alt="Camera view with detected fish, track numbers and the counting line" style={{ display: hasFrame ? 'block' : 'none' }} />
        {!hasFrame && (
          <div className="feed-placeholder">
            {isProcessing ? <><Spinner /><span>Waiting for the first frame…</span></>
              : connection !== 'live' ? <><Spinner /><span>Connecting to the station…</span></>
              : <><Video aria-hidden /><span>No active source. Choose one below to start counting.</span></>}
          </div>
        )}
        <div className="feed-overlay">
          {isProcessing && metrics.isLive && <Badge tone="live">LIVE</Badge>}
          {isProcessing && !metrics.isLive && <span className="feed-chip">Counting</span>}
        </div>
        {hasFrame && (
          <button className="feed-fullscreen icon-btn" onClick={fullscreen} aria-label="View full screen"><Maximize2 /></button>
        )}
      </div>
      <div className="feed-stats">
        <div><span className="muted">Frame</span><span className="num">{metrics.frameNumber ? formatNumber(metrics.frameNumber) : '—'}</span></div>
        <div><span className="muted">Speed</span><span className="num">{isProcessing && metrics.fps ? `${metrics.fps.toFixed(1)} fps` : '—'}</span></div>
        <div><span className="muted">In frame</span><span className="num">{metrics.activeTracks}</span></div>
        <div><span className="muted">Source</span><span>{metrics.sourceType || '—'}</span></div>
      </div>
    </div>
  )
}

/* ── Live counts ────────────────────────────────────────────────────────── */
function LiveCounts({ user }: { user: User }) {
  const { metrics } = useStation()
  return (
    <Card title="Fish counted" icon={<ScanLine aria-hidden />} sub="Counted as they cross the line, downstream only">
      <div className="stack">
        <LiveNumber value={metrics.counts.total} className="hero-figure" />
        <ClassTiles counts={metrics.counts} compact={user.preferences.compact_numbers} focus={user.preferences.size_focus} />
        <ClassBar counts={metrics.counts} legend={false} />
      </div>
    </Card>
  )
}

/* ── Source forms ───────────────────────────────────────────────────────── */
function useRememberPreference() {
  const { setUser } = useAuth()
  return useCallback((patch: Record<string, unknown>) => {
    api<{ user: User }>('/api/me/preferences', { method: 'PATCH', json: patch }).then((r) => setUser(r.user)).catch(() => {})
  }, [setUser])
}

function CameraForm({ disabled, onStart }: { disabled: boolean; onStart: (index: number) => Promise<void> }) {
  const user = useUser()
  const [index, setIndex] = useState(user.preferences.camera_index ?? 0)
  const [busy, setBusy] = useState(false)
  return (
    <div className="stack">
      <div className="field">
        <span className="field-label" id="cam-label">Station camera</span>
        <div className="stepper" role="group" aria-labelledby="cam-label">
          <button type="button" className="icon-btn" onClick={() => setIndex((i) => Math.max(0, i - 1))} disabled={index === 0} aria-label="Previous camera"><Minus /></button>
          <output aria-live="polite" className="stepper-value">Camera {index}</output>
          <button type="button" className="icon-btn" onClick={() => setIndex((i) => Math.min(9, i + 1))} disabled={index === 9} aria-label="Next camera"><Plus /></button>
        </div>
        <span className="field-hint">0 is usually the built-in camera, 1 a USB camera. This is a camera on the counting computer, not this phone.</span>
      </div>
      <Button variant="primary" size="lg" block icon={<Play />} loading={busy} disabled={disabled}
        onClick={async () => { setBusy(true); try { await onStart(index) } finally { setBusy(false) } }}>
        Start camera {index}
      </Button>
    </div>
  )
}

function UploadForm({ disabled, onUpload }: { disabled: boolean; onUpload: (file: File, onProgress: (f: number) => void) => Promise<{ abort: () => void; promise: Promise<unknown> }> }) {
  const [file, setFile] = useState<File | null>(null)
  const [over, setOver] = useState(false)
  const [progress, setProgress] = useState<number | null>(null)
  const abortRef = useRef<(() => void) | null>(null)

  const pick = (f: File | undefined | null) => { if (f) setFile(f) }
  const onDrop = (e: DragEvent) => { e.preventDefault(); setOver(false); pick(e.dataTransfer.files?.[0]) }
  const isImage = file?.type.startsWith('image/')

  const start = async () => {
    if (!file) return
    setProgress(0)
    try {
      const h = await onUpload(file, setProgress)
      abortRef.current = h.abort
      await h.promise
      setFile(null)
    } catch { /* already shown to the user by the page */ } finally { setProgress(null); abortRef.current = null }
  }

  return (
    <div className="stack">
      {!file ? (
        <label className={cx('dropzone', over && 'is-over')} onDragOver={(e) => { e.preventDefault(); setOver(true) }} onDragLeave={() => setOver(false)} onDrop={onDrop}>
          <Upload aria-hidden />
          <strong>Choose a video or photo</strong>
          <span className="small">MP4, MOV, AVI, JPG or PNG · up to 500 MB</span>
          <input type="file" accept="video/*,image/*" disabled={disabled} onChange={(e: ChangeEvent<HTMLInputElement>) => pick(e.target.files?.[0])} aria-label="Choose a video or photo to count" />
        </label>
      ) : (
        <div className="file-row">
          <span className="list-item-icon">{isImage ? <ImageIcon aria-hidden /> : <FileVideo aria-hidden />}</span>
          <div className="grow">
            <div className="truncate" style={{ fontWeight: 600 }}>{file.name}</div>
            <div className="small muted">{formatBytes(file.size)} · {isImage ? 'Photo: counted in one pass' : 'Video: counted as fish cross the line'}</div>
          </div>
          {progress === null && <button className="icon-btn" onClick={() => setFile(null)} aria-label="Remove file"><X /></button>}
        </div>
      )}
      {progress !== null && (
        <div className="stack-sm">
          <ProgressBar value={progress} label="Upload progress" />
          <div className="row-between small"><span className="secondary">Uploading… {Math.round(progress * 100)}%</span>
            <button className="link-btn" onClick={() => abortRef.current?.()}>Cancel</button></div>
        </div>
      )}
      <Button variant="primary" size="lg" block icon={<Upload />} disabled={!file || disabled || progress !== null} onClick={start}>
        Upload &amp; count
      </Button>
    </div>
  )
}

function BatchForm({ disabled, onUpload }: { disabled: boolean; onUpload: (files: File[], onProgress: (f: number) => void) => Promise<{ abort: () => void; promise: Promise<unknown> }> }) {
  const [files, setFiles] = useState<File[]>([])
  const [progress, setProgress] = useState<number | null>(null)
  const abortRef = useRef<(() => void) | null>(null)
  const previews = useMemo(() => files.slice(0, 8).map((f) => URL.createObjectURL(f)), [files])
  useEffect(() => () => previews.forEach((u) => URL.revokeObjectURL(u)), [previews])
  const size = files.reduce((a, f) => a + f.size, 0)

  const start = async () => {
    setProgress(0)
    try {
      const h = await onUpload(files, setProgress)
      abortRef.current = h.abort
      await h.promise
      setFiles([])
    } catch { /* already shown to the user by the page */ } finally { setProgress(null); abortRef.current = null }
  }

  return (
    <div className="stack">
      <label className="dropzone">
        <Images aria-hidden />
        <strong>{files.length ? `${files.length} photos selected` : 'Choose photos'}</strong>
        <span className="small">{files.length ? `${formatBytes(size)} · tap to change` : 'Each photo is counted on its own, with an annotated copy'}</span>
        <input type="file" accept="image/*" multiple disabled={disabled} onChange={(e) => setFiles(Array.from(e.target.files ?? []))} aria-label="Choose photos to count" />
      </label>
      {files.length > 0 && (
        <div className="thumbs" aria-label="Selected photos">
          {previews.map((u, i) => <img key={u} src={u} alt={files[i].name} />)}
          {files.length > previews.length && <span className="thumb-more">+{files.length - previews.length}</span>}
        </div>
      )}
      {progress !== null && (
        <div className="stack-sm">
          <ProgressBar value={progress} label="Upload progress" />
          <div className="row-between small"><span className="secondary">Uploading… {Math.round(progress * 100)}%</span>
            <button className="link-btn" onClick={() => abortRef.current?.()}>Cancel</button></div>
        </div>
      )}
      <Button variant="primary" size="lg" block icon={<Images />} disabled={!files.length || disabled || progress !== null} onClick={start}>
        Count {files.length || ''} {files.length === 1 ? 'photo' : 'photos'}
      </Button>
    </div>
  )
}

function UrlForm({ disabled, onStart }: { disabled: boolean; onStart: (url: string) => Promise<void> }) {
  const user = useUser()
  const [url, setUrl] = useState(user.preferences.stream_url ?? '')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!/^(https?|rtsp|rtmp):\/\//i.test(url.trim())) { setError('Start the address with http://, https://, rtsp:// or rtmp://'); return }
    setError(null)
    setBusy(true)
    try { await onStart(url.trim()) } catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }
  return (
    <form className="stack" onSubmit={submit} noValidate>
      <TextField label="Stream or video address" type="url" inputMode="url" autoCapitalize="off" autoCorrect="off" spellCheck={false}
        placeholder="rtsp://192.168.1.45:8080/h264.sdp" value={url} onChange={(e) => setUrl(e.target.value)} error={error}
        hint="A phone running an IP-camera app on the hatchery Wi-Fi, an RTSP camera, or a direct video link." />
      <div className="chips" aria-label="Example addresses">
        {['rtsp://192.168.1.', 'http://192.168.1.'].map((p) => (
          <button key={p} type="button" className="chip" onClick={() => setUrl(p)}>{p}…</button>
        ))}
      </div>
      <Button type="submit" variant="primary" size="lg" block icon={<Play />} loading={busy} disabled={disabled}>Start counting stream</Button>
    </form>
  )
}

/* ── Last run & batch results ───────────────────────────────────────────── */
function LastRunCard() {
  const { lastRun } = useStation()
  if (!lastRun) return null
  const counts = normaliseCounts(lastRun.counts)
  return (
    <Card title="Last saved count" icon={<CircleCheck aria-hidden />} action={<Link to={`/history/${encodeURIComponent(lastRun.run_id)}`} className="btn btn-sm btn-outline">Open report</Link>}>
      <div className="stack">
        <div className="row" style={{ alignItems: 'baseline', gap: 10 }}>
          <span className="stat-value">{formatNumber(counts.total)}</span><span className="secondary">fish</span>
          {lastRun.corrected_total != null && <span className="small muted">· calibrated {formatNumber(lastRun.corrected_total)}</span>}
        </div>
        <ClassBar counts={counts} />
        {lastRun.warning && <Callout tone="warning" icon={<TriangleAlert />}>{lastRun.warning}</Callout>}
        <span className="xsmall muted mono truncate">{lastRun.run_id}</span>
      </div>
    </Card>
  )
}

function BatchResults() {
  const { batch } = useStation()
  if (!batch.progress && !batch.results) return null
  return (
    <Card title="Photo batch" icon={<Images aria-hidden />}>
      {batch.progress && (
        <div className="stack-sm" aria-live="polite">
          <ProgressBar value={batch.progress.index / batch.progress.total} label="Batch progress" />
          <span className="small secondary">Counting {batch.progress.index} of {batch.progress.total}: {batch.progress.filename}</span>
        </div>
      )}
      {batch.results && (
        <div className="stack">
          <div className="row" style={{ alignItems: 'baseline', gap: 10 }}>
            <span className="stat-value">{formatNumber(batch.results.batch_totals.total)}</span>
            <span className="secondary">fish in {batch.results.total_files} photos</span>
          </div>
          <ClassBar counts={batch.results.batch_totals} />
          <div className="batch-grid">
            {batch.results.results.map((r, i) => (
              <figure key={`${r.filename}-${i}`} className={cx('batch-item', r.status === 'error' && 'is-error')}>
                {r.annotated_image ? <img src={`data:image/jpeg;base64,${r.annotated_image}`} alt={`${r.filename}, annotated`} loading="lazy" />
                  : <div className="batch-noimg"><CircleAlert aria-hidden /></div>}
                <figcaption>
                  <span className="truncate small" style={{ fontWeight: 600 }}>{r.filename}</span>
                  {r.status === 'success' && r.counts ? (
                    <span className="xsmall secondary">{formatNumber(r.counts.total)} fish · {CLASS_KEYS.filter((k) => r.counts![k]).map((k) => `${CLASS_LABEL[k]} ${r.counts![k]}`).join(', ') || 'none detected'}</span>
                  ) : <span className="xsmall" style={{ color: 'var(--danger)' }}>{r.error || 'Could not be counted'}</span>}
                </figcaption>
              </figure>
            ))}
          </div>
        </div>
      )}
    </Card>
  )
}

/* ── Page ───────────────────────────────────────────────────────────────── */
export function CountPage() {
  const user = useUser()
  const station = useStation()
  const toast = useToast()
  const remember = useRememberPreference()
  const [params, setParams] = useSearchParams()
  const fromUrl = params.get('source') as SourceKind | null
  const [source, setSource] = useState<SourceKind>(
    fromUrl && SOURCES.some((s) => s.value === fromUrl) ? fromUrl : user.preferences.default_source ?? 'camera')
  const [confirmReset, setConfirmReset] = useState(false)
  const [stopping, setStopping] = useState(false)

  usePageMeta({
    title: 'Live count',
    subtitle: station.isProcessing ? `Counting · ${station.job?.label ?? 'source'}` : 'Ready to count',
  }, [station.isProcessing, station.job?.label])

  const chooseSource = (s: SourceKind) => { setSource(s); setParams({ source: s }, { replace: true }) }

  const report = (err: unknown) => {
    if (err instanceof ApiError && err.code === 'aborted') return
    const tone = err instanceof ApiError && (err.isRateLimited || err.code === 'busy' || err.status === 409) ? 'warning' : 'error'
    toast.show({ tone, message: errorMessage(err), id: 'count-action' })
  }

  const othersJob = station.isProcessing && station.job?.started_by && station.job.started_by !== (user.name || user.email)
  const disabled = station.isProcessing || station.connection === 'offline'

  const stop = async () => {
    setStopping(true)
    try { await station.stop(); toast.show({ tone: 'info', message: 'Stopping. The run is being saved…', id: 'count-action' }) }
    catch (err) { report(err) } finally { setStopping(false) }
  }
  const reset = async () => {
    setConfirmReset(false)
    try { await station.reset(); toast.show({ tone: 'info', message: station.isProcessing ? 'Counts reset. A new record has started.' : 'Counts cleared.', id: 'count-action' }) }
    catch (err) { report(err) }
  }

  return (
    <div className="page count-page">
      {othersJob && (
        <Callout tone="info" icon={<ScanLine />}>
          <strong>{station.job!.started_by}</strong> is counting {station.job!.label}. You can watch live, or stop it to start your own.
        </Callout>
      )}

      {/* Two columns on desktop. On phones the slots interleave: the source picker
          comes right after the feed while idle, the live counters while counting. */}
      <div className={cx('grid grid-lg-main count-layout', station.isProcessing && 'is-counting')}>
        <div className="stack">
          <div className="slot-feed"><LiveFeed /></div>
          <div className="slot-counts"><LiveCounts user={user} /></div>
        </div>

        <div className="stack">
          <div className="slot-source">
          <Card title={station.isProcessing ? 'Count in progress' : 'Choose a source'}
            action={station.isProcessing ? <Badge tone="live">Counting</Badge> : undefined}>
            <div className="stack">
              <Segmented<SourceKind> label="Source" value={source} onChange={chooseSource}
                options={SOURCES.map((s) => ({ value: s.value, label: s.label, icon: s.icon }))} />
              {station.isProcessing && <p className="small secondary">Stop the current count before starting another.</p>}
              {source === 'camera' && <CameraForm disabled={disabled} onStart={async (i) => {
                try { await station.startCamera(i); remember({ camera_index: i }); toast.show({ tone: 'info', message: `Starting camera ${i}…`, id: 'count-action' }) } catch (err) { report(err) }
              }} />}
              {source === 'upload' && <UploadForm disabled={disabled} onUpload={async (file, onProgress) => {
                try {
                  const h = await station.uploadFile(file, onProgress)
                  h.promise.catch(report)
                  return h
                } catch (err) { report(err); throw err }
              }} />}
              {source === 'batch' && <BatchForm disabled={disabled} onUpload={async (files, onProgress) => {
                try {
                  const h = await station.uploadBatch(files, onProgress)
                  h.promise.catch(report)
                  return h
                } catch (err) { report(err); throw err }
              }} />}
              {source === 'url' && <UrlForm disabled={disabled} onStart={async (u) => {
                await station.processUrl(u)
                remember({ stream_url: u })
                toast.show({ tone: 'info', message: 'Connecting to the stream…', id: 'count-action' })
              }} />}
              <div className="count-controls">
                <Button variant="danger" icon={<Square />} onClick={stop} loading={stopping} disabled={!station.isProcessing}>Stop</Button>
                <Button variant="outline" icon={<RotateCcw />} onClick={() => setConfirmReset(true)}>Reset counts</Button>
              </div>
            </div>
          </Card>
          </div>
          <div className="slot-last"><LastRunCard /></div>
          <div className="slot-batch"><BatchResults /></div>
        </div>
      </div>

      {station.isProcessing && (
        <div className="action-bar" role="region" aria-label="Count controls">
          <div className="action-bar-total"><span className="xsmall muted">Counted</span><LiveNumber value={station.metrics.counts.total} className="num" /></div>
          <Button variant="outline" icon={<RotateCcw />} onClick={() => setConfirmReset(true)} aria-label="Reset counts" iconOnly />
          <Button variant="danger" icon={<Square />} onClick={stop} loading={stopping}>Stop &amp; save</Button>
        </div>
      )}

      <ConfirmDialog open={confirmReset} onClose={() => setConfirmReset(false)} onConfirm={reset} danger
        title="Reset counts?" confirmLabel="Reset"
        message={station.isProcessing
          ? 'The current record is closed with the fish counted so far, and a new record starts from zero.'
          : 'The counters on screen go back to zero. Saved runs are not affected.'} />
    </div>
  )
}
