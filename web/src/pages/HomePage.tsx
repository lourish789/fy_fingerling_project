import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, Camera, CircleAlert, ClipboardCheck, History as HistoryIcon, Images, Link2, Target, Upload, Fish } from 'lucide-react'
import { useUser } from '../auth/AuthProvider'
import { useStation } from '../station/StationProvider'
import { useApi } from '../hooks/useApi'
import { usePageMeta } from '../components/layout/pageMeta'
import { Badge, Card, EmptyState, ErrorState, ProgressBar, Skeleton, SkeletonList } from '../components/ui/primitives'
import { LiveNumber, RunRow } from '../components/counts'
import { formatNumber, formatPercent, formatRelative, greeting } from '../lib/format'
import type { Insights, RunList } from '../lib/types'

const QUICK = [
  { source: 'camera', title: 'Live camera', body: 'Count fish passing the station camera', icon: <Camera /> },
  { source: 'upload', title: 'Upload video', body: 'Count a recorded clip or one photo', icon: <Upload /> },
  { source: 'batch', title: 'Photo batch', body: 'Count many photos at once', icon: <Images /> },
  { source: 'url', title: 'Stream or link', body: 'Phone IP camera, RTSP or video URL', icon: <Link2 /> },
]

function StationCard() {
  const { isProcessing, job, metrics, connection } = useStation()
  if (isProcessing) {
    return (
      <Card className="station-card is-live" title="Counting now" action={<Badge tone="live">LIVE</Badge>}
        sub={job ? `${job.label}${job.started_by ? ` · started by ${job.started_by}` : ''}${job.started_at ? ` · ${formatRelative(job.started_at)}` : ''}` : undefined}>
        <div className="row-between" style={{ alignItems: 'flex-end' }}>
          <div className="stat">
            <span className="stat-label">Fish counted so far</span>
            <LiveNumber value={metrics.counts.total} className="hero-figure" />
          </div>
          <Link to="/count" className="btn btn-primary">Open live view<ArrowRight /></Link>
        </div>
      </Card>
    )
  }
  return (
    <Card className="station-card" title="Counting station" sub={connection === 'live' ? 'Ready. No count is running.' : 'Connecting to the station…'}>
      <div className="row-between wrap">
        <p className="secondary small" style={{ maxWidth: '38ch' }}>Pick a source below, or open the live view to set up the camera and counting line.</p>
        <Link to="/count" className="btn btn-primary">Start a count<ArrowRight /></Link>
      </div>
    </Card>
  )
}

function TodayCard({ insights, loading, target }: { insights: Insights | null; loading: boolean; target: number }) {
  const fish = insights?.today.fish ?? 0
  const runs = insights?.today.runs ?? 0
  return (
    <Card title="Today" icon={<Target aria-hidden />} action={<Link to="/insights" className="small">Insights</Link>}>
      {loading && !insights ? (
        <div className="stack-sm"><Skeleton width={140} height={48} /><Skeleton width="60%" /></div>
      ) : (
        <div className="stack">
          <div className="row" style={{ alignItems: 'baseline', gap: 10 }}>
            <span className="hero-figure">{formatNumber(fish)}</span>
            <span className="secondary">fish in {runs} {runs === 1 ? 'run' : 'runs'}</span>
          </div>
          {target > 0 ? (
            <div className="stack-sm">
              <ProgressBar value={fish / target} label="Progress toward today's target" />
              <div className="row-between small">
                <span className="secondary">{formatPercent(Math.min(1, fish / target))} of {formatNumber(target)} target</span>
                <span className="muted">{fish >= target ? 'Target reached' : `${formatNumber(target - fish)} to go`}</span>
              </div>
            </div>
          ) : (
            <Link to="/settings#hatchery" className="small">Set a daily target</Link>
          )}
          {insights && insights.period.runs > 0 && (
            <div className="row small muted" style={{ gap: 6 }}>
              Last 7 days: <strong className="secondary">{formatNumber(insights.period.fish)}</strong> fish in {insights.period.runs} runs
            </div>
          )}
        </div>
      )}
    </Card>
  )
}

export function HomePage() {
  const user = useUser()
  const { lastRun } = useStation()
  usePageMeta({ title: 'Home', subtitle: user.preferences.hatchery_name || undefined })
  const insights = useApi<Insights>(`/api/insights?days=7&tz_offset=${new Date().getTimezoneOffset()}`)
  const recent = useApi<RunList>('/api/runs?limit=5')
  const { reload: reloadInsights } = insights
  const { reload: reloadRecent } = recent

  useEffect(() => { if (lastRun) { reloadInsights(); reloadRecent() } }, [lastRun, reloadInsights, reloadRecent])

  const firstName = (user.name || user.email).split(' ')[0]

  return (
    <div className="page">
      <section className="home-hello">
        <p className="secondary">{greeting()},</p>
        <h2 className="home-name">{firstName}</h2>
      </section>

      <div className="grid grid-lg-main">
        <div className="stack">
          <StationCard />
          <TodayCard insights={insights.data} loading={insights.loading} target={user.preferences.daily_target ?? 0} />

          <section className="section" aria-labelledby="quick">
            <h2 id="quick" className="section-title">Start a count</h2>
            <div className="quick-grid">
              {QUICK.map((q) => (
                <Link key={q.source} to={`/count?source=${q.source}`} className="quick-card">
                  <span className="quick-icon" aria-hidden>{q.icon}</span>
                  <span className="quick-title">{q.title}</span>
                  <span className="quick-body">{q.body}</span>
                </Link>
              ))}
            </div>
          </section>
        </div>

        <div className="stack">
          <Card flush title="Recent activity" icon={<HistoryIcon aria-hidden />} action={<Link to="/history" className="small" style={{ paddingRight: 16 }}>View all</Link>}>
            {recent.loading ? <SkeletonList rows={4} />
              : recent.error ? <ErrorState icon={<CircleAlert />} message={recent.error.message} onRetry={recent.reload} />
              : recent.data && recent.data.runs.length ? (
                <div className="list">{recent.data.runs.map((r) => <RunRow key={r.run_id} run={r} />)}</div>
              ) : (
                <EmptyState icon={<Fish />} title="No counts yet" action={<Link to="/count" className="btn btn-primary">Start your first count</Link>}>
                  Every count you run is saved here with its report and fish log.
                </EmptyState>
              )}
          </Card>

          <Card title="Before you count" icon={<ClipboardCheck aria-hidden />}>
            <ul className="checklist">
              <li>Camera directly above the channel, at its marked height.</li>
              <li>Only the channel in frame: no pavement, puddles or people.</li>
              <li>Water flows from the top of the picture to the bottom.</li>
              <li>Run the empty channel for 2 minutes first. The count must stay at 0.</li>
            </ul>
            <Link to="/settings#guide" className="small">Read the full counting guide</Link>
          </Card>
        </div>
      </div>
    </div>
  )
}
