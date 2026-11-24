import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { CircleAlert, Fish, Search, SearchX } from 'lucide-react'
import { useUser } from '../auth/AuthProvider'
import { useStation } from '../station/StationProvider'
import { usePageMeta } from '../components/layout/pageMeta'
import { Button, Card, EmptyState, ErrorState, Segmented, SkeletonList } from '../components/ui/primitives'
import { RunRow } from '../components/counts'
import { api, ApiError } from '../lib/api'
import { dayGroup, formatNumber } from '../lib/format'
import type { RunList, RunRecord } from '../lib/types'

const STATUS_FILTERS = [
  { value: '', label: 'All' },
  { value: 'completed', label: 'Completed' },
  { value: 'stopped', label: 'Stopped early' },
  { value: 'error', label: 'Errors' },
]
const PAGE = 30

export function HistoryPage() {
  const user = useUser()
  const { lastRun } = useStation()
  const [q, setQ] = useState('')
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('')
  const [scope, setScope] = useState<'mine' | 'all'>('mine')
  const [runs, setRuns] = useState<RunRecord[]>([])
  const [total, setTotal] = useState(0)
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const [nonce, setNonce] = useState(0)

  usePageMeta({ title: 'History', subtitle: loading ? undefined : `${formatNumber(total)} ${total === 1 ? 'run' : 'runs'}` }, [loading, total])

  useEffect(() => { const t = setTimeout(() => setQuery(q.trim()), 300); return () => clearTimeout(t) }, [q])

  const path = (offset: number) => {
    const p = new URLSearchParams({ limit: String(PAGE), offset: String(offset) })
    if (status) p.set('status', status)
    if (query) p.set('q', query)
    if (scope === 'all') p.set('scope', 'all')
    return `/api/runs?${p}`
  }

  useEffect(() => {
    const ctrl = new AbortController()
    setLoading(true)
    setError(null)
    api<RunList>(path(0), { signal: ctrl.signal })
      .then((r) => { setRuns(r.runs); setTotal(r.total); setHasMore(r.has_more) })
      .catch((e) => { if (!ctrl.signal.aborted) setError(e instanceof ApiError ? e : new ApiError(String(e), 0, 'unknown')) })
      .finally(() => { if (!ctrl.signal.aborted) setLoading(false) })
    return () => ctrl.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, query, scope, nonce, lastRun?.run_id])

  const loadMore = async () => {
    setLoadingMore(true)
    try {
      const r = await api<RunList>(path(runs.length))
      setRuns((prev) => [...prev, ...r.runs.filter((x) => !prev.some((p) => p.run_id === x.run_id))])
      setHasMore(r.has_more)
      setTotal(r.total)
    } catch (e) {
      setError(e instanceof ApiError ? e : null)
    } finally { setLoadingMore(false) }
  }

  const groups = useMemo(() => {
    const out: { label: string; runs: RunRecord[]; fish: number }[] = []
    for (const r of runs) {
      const label = dayGroup(r.started_at || r.created_at)
      const g = out[out.length - 1]
      if (g && g.label === label) { g.runs.push(r); g.fish += r.total }
      else out.push({ label, runs: [r], fish: r.total })
    }
    return out
  }, [runs])

  const filtered = !!(status || query)

  return (
    <div className="page page-narrow">
      <div className="stack-sm history-controls">
        <div className="input-wrap">
          <Search className="input-icon" aria-hidden />
          <input className="input has-icon" type="search" placeholder="Search by source or run ID" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search runs" />
        </div>
        <div className="row-between wrap" style={{ rowGap: 8 }}>
          <div className="chips" role="group" aria-label="Filter by status">
            {STATUS_FILTERS.map((f) => (
              <button key={f.value} className="chip" aria-pressed={status === f.value} onClick={() => setStatus(f.value)}>{f.label}</button>
            ))}
          </div>
          {user.role === 'admin' && (
            <div style={{ minWidth: 200 }}>
              <Segmented compact label="Whose runs" value={scope} onChange={setScope}
                options={[{ value: 'mine', label: 'Mine' }, { value: 'all', label: 'Everyone' }]} />
            </div>
          )}
        </div>
      </div>

      {loading ? (
        <Card flush><SkeletonList rows={6} /></Card>
      ) : error && !runs.length ? (
        <Card><ErrorState icon={<CircleAlert />} message={error.message} onRetry={() => setNonce((n) => n + 1)} /></Card>
      ) : !runs.length ? (
        <Card>
          {filtered ? (
            <EmptyState icon={<SearchX />} title="No runs match" action={<Button onClick={() => { setQ(''); setStatus('') }}>Clear filters</Button>}>
              Try a different search or status.
            </EmptyState>
          ) : (
            <EmptyState icon={<Fish />} title="No counts yet" action={<Link to="/count" className="btn btn-primary">Start a count</Link>}>
              Each count is saved here with a printable report, a fish-by-fish log and spot-check photos.
            </EmptyState>
          )}
        </Card>
      ) : (
        <>
          {groups.map((g) => (
            <section key={g.label} className="section" aria-label={g.label}>
              <h2 className="section-title"><span>{g.label}</span><span className="muted num" style={{ fontWeight: 500 }}>{formatNumber(g.fish)} fish</span></h2>
              <Card flush><div className="list">{g.runs.map((r) => <RunRow key={r.run_id} run={r} showOwner={scope === 'all'} />)}</div></Card>
            </section>
          ))}
          {hasMore && <Button block onClick={loadMore} loading={loadingMore}>Load more</Button>}
        </>
      )}
    </div>
  )
}
