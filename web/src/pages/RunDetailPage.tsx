import { useCallback, useRef } from 'react'
import { Link, useParams } from 'react-router-dom'
import { CircleAlert, Download, ExternalLink, FileText, FolderX, Images, ScanSearch, TriangleAlert } from 'lucide-react'
import { useApi } from '../hooks/useApi'
import { usePageMeta } from '../components/layout/pageMeta'
import { Callout, Card, EmptyState, ErrorState, Skeleton } from '../components/ui/primitives'
import { ClassBar, StatusBadge } from '../components/counts'
import { api, apiUrl } from '../lib/api'
import {
  CLASS_KEYS, CLASS_LABEL, RUN_KIND_LABEL, formatBytes, formatDateTime, formatDuration, formatNumber, normaliseCounts,
} from '../lib/format'
import type { RunDetail } from '../lib/types'
import { demoBackend } from '../demo/registry'

const SETTING_LABELS: Record<string, string> = {
  model_file: 'Model file',
  model_sha256_12: 'Model fingerprint',
  confidence_threshold: 'Confidence threshold',
  nms_iou_threshold: 'Overlap (NMS) threshold',
  counting_mode: 'Counting mode',
  count_direction: 'Counted direction',
  counting_line_position: 'Counting line position',
  counting_line_orientation: 'Counting line',
  min_hits: 'Detections before counting',
  max_distance_px: 'Max track jump (px)',
  max_age_frames: 'Track memory (frames)',
  roi: 'Channel region (ROI)',
}

function DetailSkeleton() {
  return (
    <div className="page page-narrow" aria-busy="true">
      <div className="card stack"><Skeleton width={160} height={52} /><Skeleton height={28} /><Skeleton width="70%" /></div>
      <div className="card stack"><Skeleton width="40%" height={18} /><Skeleton height={120} /></div>
    </div>
  )
}

export function RunDetailPage() {
  const { runId = '' } = useParams()
  const detail = useApi<RunDetail>(`/api/runs/${encodeURIComponent(runId)}`)
  const fetchedAt = useRef(Date.now())
  if (detail.loading) fetchedAt.current = Date.now()
  const d = detail.data
  const run = d?.run

  usePageMeta({
    title: run ? (RUN_KIND_LABEL[run.kind] ?? 'Run') : 'Run',
    subtitle: run ? formatDateTime(run.started_at || run.created_at) : undefined,
    back: '/history',
  }, [run?.run_id])

  /** Media tokens last 15 minutes; get a fresh one if this page has been open a while. */
  const mediaToken = useCallback(async () => {
    if (!d) return ''
    if (Date.now() - fetchedAt.current < (d.media_expires_in - 60) * 1000) return d.media_token
    const fresh = await api<RunDetail>(`/api/runs/${encodeURIComponent(runId)}`)
    fetchedAt.current = Date.now()
    detail.setData(() => fresh)
    return fresh.media_token
  }, [d, runId, detail])

  const demo = demoBackend()
  const fileUrl = (path: string, token: string, download = false) => demo ? demo.demoFileUrl(runId, path) :
    apiUrl(`/api/runs/${encodeURIComponent(runId)}/${path}?t=${encodeURIComponent(token)}${download ? '&download=1' : ''}`)

  const openFile = async (name: string, download: boolean) => {
    // Open the tab synchronously so pop-up blockers allow it, then point it at the file.
    // (With 'noopener', window.open returns null, so cut the opener link by hand instead.)
    const win = download ? null : window.open('', '_blank')
    if (win) win.opener = null
    const token = await mediaToken()
    const url = fileUrl(name, token, download)
    if (win) win.location.href = url
    else if (download) { const a = document.createElement('a'); a.href = url; a.download = name; a.rel = 'noopener'; document.body.appendChild(a); a.click(); a.remove() }
    else window.location.href = url
  }

  if (detail.loading) return <DetailSkeleton />
  if (detail.error || !d || !run) {
    return (
      <div className="page page-narrow">
        <Card>
          {detail.error?.status === 404 ? (
            <EmptyState icon={<FolderX />} title="Run not found" action={<Link to="/history" className="btn btn-primary">Back to history</Link>}>
              It may belong to another operator, or it was removed.
            </EmptyState>
          ) : <ErrorState icon={<CircleAlert />} message={detail.error?.message} onRetry={detail.reload} />}
        </Card>
      </div>
    )
  }

  const counts = normaliseCounts({ ...run.counts, total: run.total })
  const s = d.summary
  const settings = (s?.settings ?? {}) as Record<string, unknown>
  const results = Array.isArray(s?.results) ? s!.results! : []
  const fps = run.processing_seconds > 0 && run.frames_processed ? run.frames_processed / run.processing_seconds : null

  return (
    <div className="page page-narrow">
      <Card>
        <div className="stack">
          <div className="row-between" style={{ alignItems: 'flex-start' }}>
            <div className="stat">
              <span className="stat-label">Fish counted</span>
              <span className="hero-figure">{formatNumber(run.total)}</span>
            </div>
            <StatusBadge status={run.status} />
          </div>
          {run.corrected_total != null && (
            <p className="secondary">Calibrated estimate <strong style={{ color: 'var(--text-1)' }}>{formatNumber(run.corrected_total)}</strong>
              <span className="muted"> (×{run.correction_factor?.toFixed(3)})</span></p>
          )}
          {run.warning && <Callout tone="warning" icon={<TriangleAlert />}>{run.warning}</Callout>}
          <ClassBar counts={counts} size="tall" />
          <div className="mini-stats">
            <div><span className="muted xsmall">Duration</span><span>{formatDuration(run.processing_seconds)}</span></div>
            <div><span className="muted xsmall">{run.kind === 'batch' ? 'Photos' : 'Frames'}</span><span className="num">{formatNumber(run.frames_processed)}</span></div>
            <div><span className="muted xsmall">Speed</span><span className="num">{fps && run.kind !== 'batch' && run.kind !== 'image' ? `${fps.toFixed(1)} fps` : '—'}</span></div>
            <div><span className="muted xsmall">Started by</span><span className="truncate">{run.owner?.name ?? 'Unassigned'}</span></div>
          </div>
        </div>
      </Card>

      {!d.files_available && (
        <Callout tone="warning" icon={<FolderX />}>
          The files for this run are no longer on this server. Hosted servers clear their disk on restart; the hatchery laptop keeps them in <span className="mono">output/runs</span>.
        </Callout>
      )}

      {run.kind === 'image' && d.files.some((f) => f.name === 'annotated.jpg') && (
        <Card title="Annotated photo" flush>
          <MediaImage path="annotated.jpg" alt={`${run.source}, with detected fish boxed`} fileUrl={fileUrl} token={d.media_token} className="run-photo" />
        </Card>
      )}

      {results.length > 0 && (
        <Card title={`Photos (${results.length})`} icon={<Images aria-hidden />}>
          <div className="batch-grid">
            {results.map((r, i) => (
              <figure key={`${r.filename}-${i}`} className="batch-item">
                {r.image ? <MediaImage path={r.image} alt={`${r.filename}, annotated`} fileUrl={fileUrl} token={d.media_token} />
                  : <div className="batch-noimg"><CircleAlert aria-hidden /></div>}
                <figcaption>
                  <span className="truncate small" style={{ fontWeight: 600 }}>{r.filename}</span>
                  {r.status === 'success' && r.counts ? (
                    <span className="xsmall secondary">{formatNumber(r.counts.total)} fish{r.label_summary && r.label_summary !== 'No detections' ? ` · ${r.label_summary}` : ''}</span>
                  ) : <span className="xsmall" style={{ color: 'var(--danger)' }}>{r.error || 'Could not be counted'}</span>}
                </figcaption>
              </figure>
            ))}
          </div>
        </Card>
      )}

      {d.crops.length > 0 && (
        <Card title="Spot-check photos" icon={<ScanSearch aria-hidden />}
          sub={d.crops_total > d.crops.length ? `The last ${d.crops.length} of ${formatNumber(d.crops_total)} counted fish` : `${formatNumber(d.crops_total)} counted fish`}>
          <p className="small secondary" style={{ marginBottom: 12 }}>One picture per counted fish. If something other than a fish shows up here, check the framing and lighting.</p>
          <div className="crop-grid">
            {d.crops.map((c) => (
              <figure key={c.path} className={`crop class-${CLASS_KEYS.includes(c.class as never) ? c.class : 'unknown'}`}>
                <MediaImage path={c.path} alt={`Fish ${c.seq ?? ''}, ${CLASS_LABEL[c.class as keyof typeof CLASS_LABEL] ?? c.class}`} fileUrl={fileUrl} token={d.media_token} />
                <figcaption><span className="swatch" aria-hidden />#{c.seq}</figcaption>
              </figure>
            ))}
          </div>
        </Card>
      )}

      {d.files.length > 0 && (
        <Card title="Reports & data" icon={<FileText aria-hidden />} flush>
          <div className="list">
            {d.files.map((f) => (
              <div key={f.name} className="list-item">
                <span className="list-item-icon"><FileText aria-hidden /></span>
                <div className="grow">
                  <div style={{ fontWeight: 600 }}>{f.label}</div>
                  <div className="xsmall muted"><span className="mono">{f.name}</span> · {formatBytes(f.bytes)}</div>
                </div>
                {(f.name.endsWith('.html') || f.name.endsWith('.jpg')) && (
                  <button className="icon-btn" onClick={() => openFile(f.name, false)} aria-label={`Open ${f.label}`}><ExternalLink /></button>
                )}
                <button className="icon-btn" onClick={() => openFile(f.name, true)} aria-label={`Download ${f.label}`}><Download /></button>
              </div>
            ))}
          </div>
        </Card>
      )}

      <Card title="Details">
        <dl className="kv">
          <dt>Run ID</dt><dd className="mono">{run.run_id}</dd>
          <dt>Source</dt><dd>{run.source || '—'}</dd>
          <dt>Started</dt><dd>{formatDateTime(run.started_at)}</dd>
          <dt>Ended</dt><dd>{formatDateTime(run.ended_at)}</dd>
          {s?.correction_note ? (<><dt>Calibration</dt><dd>{String(s.correction_note)}</dd></>) : null}
          {Object.entries(settings).filter(([, v]) => v !== null && v !== undefined && v !== '').map(([k, v]) => (
            <SettingRow key={k} k={k} v={v} />
          ))}
        </dl>
      </Card>
    </div>
  )
}

function SettingRow({ k, v }: { k: string; v: unknown }) {
  return (<><dt>{SETTING_LABELS[k] ?? k}</dt><dd className={k.startsWith('model') ? 'mono' : undefined}>{Array.isArray(v) ? v.join(', ') : String(v)}</dd></>)
}

function MediaImage({ path, alt, fileUrl, token, className }: { path: string; alt: string; token: string; className?: string; fileUrl: (p: string, t: string) => string }) {
  return <img className={className} src={fileUrl(path, token)} alt={alt} loading="lazy" decoding="async" />
}
