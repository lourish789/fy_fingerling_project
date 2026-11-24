import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Camera, ChevronRight, Image as ImageIcon, Images, Link2, Video } from 'lucide-react'
import { CLASS_KEYS, CLASS_LABEL, RUN_KIND_LABEL, STATUS_LABEL, classShares, formatNumber, formatPercent, formatTime, normaliseCounts, statusTone } from '../lib/format'
import type { ClassKey, Counts, RunKind, RunRecord } from '../lib/types'
import { Badge, cx } from './ui/primitives'

/* ── A number that pulses when it changes (live counters) ──────────────── */
export function LiveNumber({ value, className, compact }: { value: number; className?: string; compact?: boolean }) {
  const [bump, setBump] = useState(false)
  const prev = useRef(value)
  useEffect(() => {
    if (value > prev.current) { setBump(true); const t = setTimeout(() => setBump(false), 280); prev.current = value; return () => clearTimeout(t) }
    prev.current = value
  }, [value])
  return <span className={cx(className, bump && 'bump')}>{formatNumber(value, compact)}</span>
}

/* ── Class tiles (live / run totals) ────────────────────────────────────── */
export function ClassTiles({ counts, compact, focus }: { counts: Counts; compact?: boolean; focus?: ClassKey[] }) {
  return (
    <div className="class-tiles">
      {CLASS_KEYS.map((k) => (
        <div key={k} className={cx('class-tile', `class-${k}`, focus && focus.length > 0 && !focus.includes(k) && k !== 'unknown' && 'is-dim')}>
          <div className="stat-label"><span className="swatch" aria-hidden />{CLASS_LABEL[k]}</div>
          <LiveNumber value={counts[k]} className="stat-value" compact={compact} />
        </div>
      ))}
    </div>
  )
}

/* ── Segmented class bar + legend (part of whole) ───────────────────────── */
export function ClassBar({ counts, size = 'default', legend = true }: { counts: Counts; size?: 'thin' | 'default' | 'tall'; legend?: boolean }) {
  const shares = classShares(counts)
  const sum = CLASS_KEYS.reduce((a, k) => a + counts[k], 0)
  const label = sum
    ? CLASS_KEYS.filter((k) => counts[k]).map((k) => `${CLASS_LABEL[k]} ${formatNumber(counts[k])} (${formatPercent(shares[k])})`).join(', ')
    : 'No fish classified yet'
  return (
    <div className="stack-sm">
      <div className={cx('segbar', size === 'thin' && 'segbar-thin', size === 'tall' && 'segbar-tall')} role="img" aria-label={`Class mix: ${label}`}>
        {sum > 0 && CLASS_KEYS.filter((k) => counts[k] > 0).map((k) => (
          <span key={k} className={`class-${k}`} style={{ flexGrow: counts[k], flexBasis: 0 }} title={`${CLASS_LABEL[k]}: ${formatNumber(counts[k])} (${formatPercent(shares[k])})`}>
            {size === 'tall' && shares[k] >= 0.12 ? formatPercent(shares[k]) : null}
          </span>
        ))}
      </div>
      {legend && (
        <div className="legend">
          {CLASS_KEYS.filter((k) => k !== 'unknown' || counts.unknown > 0).map((k) => (
            <span key={k} className={cx('legend-item', `class-${k}`)}>
              <span className="swatch" aria-hidden />{CLASS_LABEL[k]} <strong className="num">{formatNumber(counts[k])}</strong>
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

/* ── Run kind icon & status badge ───────────────────────────────────────── */
const KIND_ICON: Record<RunKind, ReactNode> = {
  video: <Video aria-hidden />,
  camera: <Camera aria-hidden />,
  url: <Link2 aria-hidden />,
  image: <ImageIcon aria-hidden />,
  batch: <Images aria-hidden />,
}
export function RunKindIcon({ kind }: { kind: RunKind }) {
  return <span className="list-item-icon" title={RUN_KIND_LABEL[kind] ?? kind}>{KIND_ICON[kind] ?? <Video aria-hidden />}</span>
}

export function StatusBadge({ status }: { status: string }) {
  const tone = statusTone(status)
  return <Badge tone={tone === 'neutral' ? 'neutral' : tone}>{STATUS_LABEL[status] ?? status}</Badge>
}

/* ── Run row (history, recent activity) ─────────────────────────────────── */
export function RunRow({ run, showOwner }: { run: RunRecord; showOwner?: boolean }) {
  const counts = normaliseCounts({ ...run.counts, total: run.total })
  return (
    <Link to={`/history/${encodeURIComponent(run.run_id)}`} className="list-item run-row">
      <RunKindIcon kind={run.kind} />
      <div className="grow stack-sm" style={{ gap: 6 }}>
        <div className="row" style={{ gap: 8, minWidth: 0 }}>
          <span className="truncate" style={{ fontWeight: 600 }}>{run.source || RUN_KIND_LABEL[run.kind]}</span>
        </div>
        <div className="row small muted" style={{ gap: 8, flexWrap: 'wrap' }}>
          <span className="num">{formatTime(run.started_at || run.created_at)}</span>
          <span aria-hidden>·</span>
          <span>{RUN_KIND_LABEL[run.kind] ?? run.kind}</span>
          {showOwner && run.owner && (<><span aria-hidden>·</span><span className="truncate">{run.owner.name}</span></>)}
          {showOwner && !run.owner && (<><span aria-hidden>·</span><span>Unassigned</span></>)}
          {run.status !== 'completed' && <StatusBadge status={run.status} />}
        </div>
        <ClassBar counts={counts} size="thin" legend={false} />
      </div>
      <div className="run-total">
        <span className="run-total-n">{formatNumber(run.total, true)}</span>
        <span className="xsmall muted">fish</span>
      </div>
      <ChevronRight className="list-item-chevron" aria-hidden />
    </Link>
  )
}
