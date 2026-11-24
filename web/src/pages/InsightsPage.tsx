import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ChartColumn, CircleAlert, Clock, Fish, Table2, Trophy } from 'lucide-react'
import { useUser } from '../auth/AuthProvider'
import { useApi } from '../hooks/useApi'
import { usePageMeta } from '../components/layout/pageMeta'
import { Button, Card, EmptyState, ErrorState, Segmented, Skeleton } from '../components/ui/primitives'
import { ClassBar } from '../components/counts'
import { DailyChart } from '../components/DailyChart'
import { CLASS_KEYS, CLASS_LABEL, RUN_KIND_LABEL, formatNumber, formatPercent, formatShortDay, normaliseCounts } from '../lib/format'
import type { Insights, RunKind } from '../lib/types'

const RANGES = [
  { value: '7', label: '7 days' },
  { value: '14', label: '14 days' },
  { value: '30', label: '30 days' },
  { value: '90', label: '90 days' },
] as const

function hourLabel(h: number): string {
  const fmt = new Intl.DateTimeFormat(undefined, { hour: 'numeric' })
  const d = new Date(2000, 0, 1, h)
  return `${fmt.format(d)}–${fmt.format(new Date(2000, 0, 1, (h + 1) % 24))}`
}

function StatTile({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="card stat">
      <span className="stat-label">{label}</span>
      <span className="stat-value">{value}</span>
      {note && <span className="stat-note">{note}</span>}
    </div>
  )
}

export function InsightsPage() {
  const user = useUser()
  const [range, setRange] = useState<(typeof RANGES)[number]['value']>('14')
  const [scope, setScope] = useState<'mine' | 'all'>('mine')
  const [table, setTable] = useState(false)
  const [classTable, setClassTable] = useState(false)
  const tz = new Date().getTimezoneOffset()
  const { data, loading, error, reload, refreshing } = useApi<Insights>(`/api/insights?days=${range}&tz_offset=${tz}${scope === 'all' ? '&scope=all' : ''}`)

  usePageMeta({ title: 'Insights', subtitle: scope === 'all' ? 'Whole station' : 'Your counts' }, [scope])

  const classes = normaliseCounts({ ...data?.classes, total: data?.period.fish ?? 0 })
  const classSum = CLASS_KEYS.reduce((a, k) => a + classes[k], 0)
  const compact = user.preferences.compact_numbers

  return (
    <div className="page">
      {/* Filters: one row, above every chart they control */}
      <div className="row-between wrap filters-row" style={{ rowGap: 8 }}>
        <div style={{ flex: '1 1 300px', maxWidth: 420 }}>
          <Segmented compact label="Time range" value={range} onChange={setRange} options={RANGES.map((r) => ({ value: r.value, label: r.label }))} />
        </div>
        {user.role === 'admin' && (
          <div style={{ flex: '0 1 220px' }}>
            <Segmented compact label="Whose counts" value={scope} onChange={setScope} options={[{ value: 'mine', label: 'Mine' }, { value: 'all', label: 'Station' }]} />
          </div>
        )}
      </div>

      {error && !data ? (
        <Card><ErrorState icon={<CircleAlert />} message={error.message} onRetry={reload} /></Card>
      ) : loading && !data ? (
        <>
          <div className="grid grid-2 grid-md-4">{[0, 1, 2, 3].map((i) => <div key={i} className="card stack-sm"><Skeleton width="60%" /><Skeleton width={90} height={28} /></div>)}</div>
          <div className="card"><Skeleton height={220} /></div>
        </>
      ) : data && data.lifetime.runs === 0 ? (
        <Card>
          <EmptyState icon={<ChartColumn />} title="Nothing to chart yet" action={<Link to="/count" className="btn btn-primary">Start a count</Link>}>
            Insights fill in as you count: daily totals, size-class mix and your busiest hours.
          </EmptyState>
        </Card>
      ) : data ? (
        <div className="stack" style={{ opacity: refreshing ? 0.6 : 1, transition: 'opacity 160ms' }} aria-busy={refreshing}>
          <div className="grid grid-2 grid-md-4">
            <StatTile label="Fish counted" value={formatNumber(data.period.fish, compact)} note={`last ${data.days} days`} />
            <StatTile label="Runs" value={formatNumber(data.period.runs)} note={`${formatNumber(data.today.runs)} today`} />
            <StatTile label="Average per run" value={formatNumber(Math.round(data.period.avg_fish_per_run))} note="fish" />
            <StatTile label="Finished cleanly" value={data.period.completed_share != null ? formatPercent(data.period.completed_share) : '—'} note="of runs completed" />
          </div>

          <div className="grid grid-lg-main">
            <Card title="Fish counted per day" icon={<ChartColumn aria-hidden />}
              action={<Button size="sm" variant="ghost" icon={<Table2 />} onClick={() => setTable((t) => !t)} aria-pressed={table}>{table ? 'Chart' : 'Table'}</Button>}>
              {table ? (
                <div style={{ maxHeight: 320, overflowY: 'auto' }}>
                  <table className="data-table">
                    <thead><tr><th>Day</th><th className="n">Fish</th><th className="n">Runs</th></tr></thead>
                    <tbody>{[...data.series].reverse().map((p) => (
                      <tr key={p.date}><td>{formatShortDay(p.date)}</td><td className="n">{formatNumber(p.fish)}</td><td className="n">{p.runs}</td></tr>
                    ))}</tbody>
                  </table>
                </div>
              ) : <DailyChart series={data.series} />}
            </Card>

            <div className="stack">
              <Card title="Size-class mix" icon={<Fish aria-hidden />}
                action={<Button size="sm" variant="ghost" icon={<Table2 />} onClick={() => setClassTable((t) => !t)} aria-pressed={classTable}>{classTable ? 'Bar' : 'Table'}</Button>}>
                {classSum === 0 ? <p className="small secondary">No fish counted in this period.</p> : classTable ? (
                  <table className="data-table">
                    <thead><tr><th>Class</th><th className="n">Fish</th><th className="n">Share</th></tr></thead>
                    <tbody>{CLASS_KEYS.map((k) => (
                      <tr key={k}><td><span className={`legend-item class-${k}`}><span className="swatch" aria-hidden />{CLASS_LABEL[k]}</span></td>
                        <td className="n">{formatNumber(classes[k])}</td><td className="n">{formatPercent(classes[k] / classSum, 1)}</td></tr>
                    ))}</tbody>
                  </table>
                ) : <ClassBar counts={classes} size="tall" />}
              </Card>

              <Card>
                <div className="stack">
                  <div className="row" style={{ gap: 12 }}>
                    <span className="list-item-icon"><Trophy aria-hidden /></span>
                    <div className="grow"><div className="small muted">Best day</div>
                      <div style={{ fontWeight: 600 }}>{data.period.best_day ? `${formatShortDay(data.period.best_day.date)} · ${formatNumber(data.period.best_day.fish)} fish` : '—'}</div></div>
                  </div>
                  <div className="row" style={{ gap: 12 }}>
                    <span className="list-item-icon"><Clock aria-hidden /></span>
                    <div className="grow"><div className="small muted">Busiest hour</div>
                      <div style={{ fontWeight: 600 }}>{data.busiest_hour != null ? hourLabel(data.busiest_hour) : '—'}</div></div>
                  </div>
                  {data.period.avg_processing_fps != null && (
                    <p className="xsmall muted">Video runs processed at {data.period.avg_processing_fps.toFixed(1)} frames/s on average. Keep fish slow enough to be seen in 6 or more frames.</p>
                  )}
                </div>
              </Card>

              {Object.keys(data.kinds).length > 0 && (
                <Card title="How you counted">
                  <ul className="kind-list">
                    {Object.entries(data.kinds).sort((a, b) => b[1] - a[1]).map(([k, n]) => (
                      <li key={k}><span>{RUN_KIND_LABEL[k as RunKind] ?? k}</span><span className="num muted">{n} {n === 1 ? 'run' : 'runs'}</span></li>
                    ))}
                  </ul>
                </Card>
              )}
            </div>
          </div>
          <p className="xsmall muted center">All time: {formatNumber(data.lifetime.fish)} fish in {formatNumber(data.lifetime.runs)} runs.</p>
        </div>
      ) : null}
    </div>
  )
}
