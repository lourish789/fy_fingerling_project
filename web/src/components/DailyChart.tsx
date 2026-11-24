import { useEffect, useMemo, useRef, useState } from 'react'
import { formatNumber, formatShortDay } from '../lib/format'

interface Point { date: string; fish: number; runs: number }

/** Round the axis top up to a clean number so ticks read 0 / 500 / 1,000 … */
export function niceScale(max: number, ticks = 4): { top: number; step: number } {
  if (max <= 0) return { top: ticks, step: 1 }
  const raw = max / ticks
  const mag = 10 ** Math.floor(Math.log10(raw))
  const norm = raw / mag
  const step = (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10) * mag
  return { top: Math.ceil(max / step) * step, step }
}

const tickLabel = (v: number, top: number) => (top >= 10_000 ? new Intl.NumberFormat(undefined, { notation: 'compact' }).format(v) : formatNumber(v))

/** Rounded data-end (4px), square at the baseline. */
function barPath(x: number, y: number, w: number, base: number): string {
  const h = base - y
  if (h <= 0) return ''
  const r = Math.min(4, w / 2, h)
  return `M${x},${base}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${base}Z`
}

/**
 * Single-series column chart: fish counted per day.
 * One colour (the title names the series, so no legend), hairline grid,
 * a per-bar hover tooltip, and only the best day labelled.
 */
export function DailyChart({ series, height = 220 }: { series: Point[]; height?: number }) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(640)
  const [hover, setHover] = useState<number | null>(null)

  useEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const ro = new ResizeObserver(([entry]) => setWidth(Math.max(240, Math.round(entry.contentRect.width))))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const pad = { l: 44, r: 8, t: 22, b: 26 }
  const plotW = width - pad.l - pad.r
  const plotH = height - pad.t - pad.b
  const max = Math.max(0, ...series.map((p) => p.fish))
  const { top, step } = niceScale(max)
  const n = series.length || 1
  const band = plotW / n
  const barW = Math.max(2, Math.min(24, band - 2)) // ≤ 24px, with at least a 2px gap between neighbours
  const y = (v: number) => pad.t + plotH - (v / top) * plotH
  const base = pad.t + plotH
  const bestIdx = max > 0 ? series.findIndex((p) => p.fish === max) : -1
  const labelEvery = Math.max(1, Math.ceil(n / Math.floor(plotW / 58)))
  const ticks = useMemo(() => Array.from({ length: Math.round(top / step) + 1 }, (_, i) => i * step), [top, step])

  const summary = max > 0
    ? `Fish counted per day over ${n} days. Highest: ${formatNumber(max)} on ${formatShortDay(series[bestIdx].date)}.`
    : `No fish counted in the last ${n} days.`

  const h = hover != null ? series[hover] : null
  const tipLeft = hover != null ? Math.min(Math.max(pad.l + band * hover + band / 2, 70), width - 70) : 0

  return (
    <div className="chart" ref={wrapRef} onPointerLeave={() => setHover(null)}>
      <svg width={width} height={height} role="img" aria-label={summary}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={pad.l} x2={width - pad.r} y1={y(t)} y2={y(t)} className={t === 0 ? 'chart-axis' : 'chart-grid'} />
            <text x={pad.l - 8} y={y(t)} className="chart-tick" textAnchor="end" dominantBaseline="middle">{tickLabel(t, top)}</text>
          </g>
        ))}
        {series.map((p, i) => {
          const x = pad.l + band * i + (band - barW) / 2
          return (
            <g key={p.date}>
              <path d={barPath(x, y(p.fish), barW, base)} className="chart-bar" data-dim={hover != null && hover !== i ? '' : undefined} />
              {i % labelEvery === 0 && (
                <text x={pad.l + band * i + band / 2} y={height - 8} className="chart-tick" textAnchor="middle">{formatShortDay(p.date)}</text>
              )}
              {i === bestIdx && hover == null && (
                <text x={x + barW / 2} y={y(p.fish) - 6} className="chart-value" textAnchor="middle">{formatNumber(p.fish, true)}</text>
              )}
              {/* Hit target: the whole column, wider than the mark */}
              <rect x={pad.l + band * i} y={pad.t} width={band} height={plotH} fill="transparent"
                onPointerEnter={() => setHover(i)} onPointerDown={() => setHover(i)} />
            </g>
          )
        })}
      </svg>
      {h && (
        <div className="chart-tip" style={{ left: tipLeft }} role="status">
          <div className="chart-tip-title">{formatShortDay(h.date)}</div>
          <div><strong className="num">{formatNumber(h.fish)}</strong> fish</div>
          <div className="muted">{h.runs} {h.runs === 1 ? 'run' : 'runs'}</div>
        </div>
      )}
    </div>
  )
}
