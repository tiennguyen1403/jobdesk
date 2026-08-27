import type { ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getHealth } from '../lib/api'
import {
  analyticsSummaryQueryKey,
  getAnalyticsSummary,
  type AnalyticsSummary,
} from '../lib/api/analytics'
import { APPLICATION_STAGES, STAGE_LABELS } from '../lib/api/applications'

// The canonical job sources, shown first and in this order so the source mix has
// a stable shape even before a provider has ingested anything; the backend always
// returns these four. Kept as strings so a future provider still renders.
const CANONICAL_SOURCES: readonly string[] = ['manual', 'capture', 'upwork', 'freelancer']

const SOURCE_LABELS: Record<string, string> = {
  manual: 'Manual',
  capture: 'Capture',
  upwork: 'Upwork',
  freelancer: 'Freelancer',
}

function sourceLabel(source: string): string {
  return SOURCE_LABELS[source] ?? source.charAt(0).toUpperCase() + source.slice(1)
}

/** AI cost is tiny per call, so four decimals (e.g. $0.0123) — matches the AI Runs page. */
function formatUsd(usd: number): string {
  return `$${usd.toFixed(4)}`
}

/** A 0–1 fraction as a whole-number percent (applied_conversion → "67%"). */
function formatPct(fraction: number): string {
  return `${Math.round(fraction * 100)}%`
}

export default function Dashboard() {
  const {
    data: summary,
    isLoading,
    isError,
  } = useQuery({
    queryKey: analyticsSummaryQueryKey(),
    queryFn: () => getAnalyticsSummary(),
  })

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-slate-400">
          Your JobDesk analytics overview — jobs, the application funnel, match quality and AI
          spend.
        </p>
      </div>

      <HealthPanel />

      {isLoading ? (
        <p className="text-slate-400">Loading analytics…</p>
      ) : isError ? (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-6">
          <p className="text-red-400">
            Could not load analytics. Make sure the backend is running (docker compose up).
          </p>
        </div>
      ) : summary ? (
        <AnalyticsView summary={summary} />
      ) : null}
    </div>
  )
}

/** The four analytics panels plus the headline figures, rendered from one payload. */
function AnalyticsView({ summary }: { summary: AnalyticsSummary }) {
  const { jobs, match, pipeline, ai } = summary

  // Canonical sources first (backend guarantees the four), then any extra source
  // a future provider adds — appended in whatever order the payload carries them.
  const sourceEntries: Array<[string, number]> = [
    ...CANONICAL_SOURCES.map((s): [string, number] => [s, jobs.by_source[s] ?? 0]),
    ...Object.entries(jobs.by_source).filter(([s]) => !CANONICAL_SOURCES.includes(s)),
  ]
  const sourceMax = Math.max(1, ...sourceEntries.map(([, n]) => n))

  const funnel = APPLICATION_STAGES.map((stage) => ({
    stage,
    count: pipeline.by_status[stage] ?? 0,
  }))
  const funnelMax = Math.max(1, ...funnel.map((f) => f.count))

  // High → low reads like a quality ranking; each band gets its own tone.
  const bands = [
    { label: 'High (70–100)', value: match.bands.high, tone: 'bg-emerald-500' },
    { label: 'Medium (40–69)', value: match.bands.medium, tone: 'bg-amber-500' },
    { label: 'Low (0–39)', value: match.bands.low, tone: 'bg-rose-500' },
  ]
  const bandMax = Math.max(1, ...bands.map((b) => b.value))

  const featureMax = Math.max(1, ...ai.by_feature.map((f) => f.cost_usd))

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat
          label="Jobs"
          value={jobs.total.toLocaleString()}
          hint={`${match.scored.toLocaleString()} scored`}
        />
        <Stat
          label="Pipeline"
          value={pipeline.total.toLocaleString()}
          hint={`${formatPct(pipeline.applied_conversion)} applied`}
        />
        <Stat
          label="AI spend"
          value={formatUsd(ai.total_cost_usd)}
          hint={`${(ai.input_tokens + ai.output_tokens).toLocaleString()} tokens`}
        />
        <Stat
          label="Part-time fit"
          value={match.part_time_fit.toLocaleString()}
          hint="jobs match your scope"
        />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Panel title="Source mix" subtitle="Where the tracked jobs came from.">
          {jobs.total === 0 ? (
            <EmptyLine text="No jobs yet — add one manually or connect a source." />
          ) : (
            sourceEntries.map(([source, count]) => (
              <Bar
                key={source}
                label={sourceLabel(source)}
                value={count}
                max={sourceMax}
                tone="bg-emerald-500"
              />
            ))
          )}
        </Panel>

        <Panel title="Pipeline funnel" subtitle="Applications by stage (a live snapshot).">
          {pipeline.total === 0 ? (
            <EmptyLine text="No applications tracked yet." />
          ) : (
            funnel.map(({ stage, count }) => (
              <Bar
                key={stage}
                label={STAGE_LABELS[stage]}
                value={count}
                max={funnelMax}
                tone="bg-sky-500"
              />
            ))
          )}
        </Panel>

        <Panel
          title="Match-score distribution"
          subtitle={`${match.scored.toLocaleString()} scored · ${match.unscored.toLocaleString()} unscored · ${match.part_time_fit.toLocaleString()} part-time fit`}
        >
          {match.scored === 0 ? (
            <EmptyLine text="No jobs have been match-scored yet." />
          ) : (
            bands.map((b) => (
              <Bar key={b.label} label={b.label} value={b.value} max={bandMax} tone={b.tone} />
            ))
          )}
        </Panel>

        <Panel
          title="AI spend by feature"
          subtitle={`${formatUsd(ai.total_cost_usd)} total across all Claude calls.`}
        >
          {ai.by_feature.length === 0 ? (
            <EmptyLine text="No AI runs logged yet — score a match or draft in the Studio." />
          ) : (
            ai.by_feature.map((f) => (
              <Bar
                key={f.feature}
                label={`${f.feature} · ${f.runs} run${f.runs === 1 ? '' : 's'}`}
                value={f.cost_usd}
                max={featureMax}
                valueText={formatUsd(f.cost_usd)}
                tone="bg-violet-500"
              />
            ))
          )}
          {ai.recent.length >= 2 ? (
            <div className="pt-2">
              <p className="mb-1 text-xs uppercase tracking-wide text-slate-500">
                Daily spend · last {ai.days} days
              </p>
              <Sparkline points={ai.recent.map((d) => d.cost_usd)} />
            </div>
          ) : null}
        </Panel>
      </div>
    </div>
  )
}

/** Compact API / database health strip — the original Dashboard signal, kept. */
function HealthPanel() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['health'],
    queryFn: getHealth,
  })

  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900 p-4">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
        <span className="text-xs uppercase tracking-wide text-slate-500">System</span>
        {isLoading ? (
          <span className="text-sm text-slate-400">Checking API…</span>
        ) : isError ? (
          <span className="text-sm text-red-400">
            Could not reach the API — make sure the backend is running (docker compose up).
          </span>
        ) : data ? (
          <>
            <span className="flex items-center gap-2 text-sm text-slate-300">
              <Dot ok={data.status === 'ok'} /> API
              <span className="font-mono text-xs text-slate-400">{data.status}</span>
            </span>
            <span className="flex items-center gap-2 text-sm text-slate-300">
              <Dot ok={data.db} /> Database
              <span className="font-mono text-xs text-slate-400">
                {data.db ? 'connected' : 'down'}
              </span>
            </span>
          </>
        ) : null}
      </div>
    </section>
  )
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
      <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums text-slate-100">{value}</p>
      {hint ? <p className="mt-1 text-xs text-slate-500">{hint}</p> : null}
    </div>
  )
}

function Panel({
  title,
  subtitle,
  children,
}: {
  title: string
  subtitle?: string
  children: ReactNode
}) {
  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900 p-6">
      <h2 className="text-lg font-semibold">{title}</h2>
      {subtitle ? <p className="mt-0.5 text-sm text-slate-400">{subtitle}</p> : null}
      <div className="mt-4 space-y-3">{children}</div>
    </section>
  )
}

/**
 * One labelled horizontal bar. Width is value/max, so a caller passing max=1 for
 * an all-zero series renders empty bars (no divide-by-zero, no crash). `valueText`
 * overrides the right-hand figure for money/percent; otherwise it's the raw count.
 */
function Bar({
  label,
  value,
  max,
  valueText,
  tone = 'bg-emerald-500',
}: {
  label: string
  value: number
  max: number
  valueText?: string
  tone?: string
}) {
  const pct = max > 0 ? (value / max) * 100 : 0
  return (
    <div className="space-y-1">
      <div className="flex items-baseline justify-between gap-3 text-sm">
        <span className="truncate text-slate-300">{label}</span>
        <span className="shrink-0 font-mono tabular-nums text-slate-400">
          {valueText ?? value.toLocaleString()}
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-slate-800">
        <div className={`h-full rounded-full ${tone}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

/** Dependency-free daily-spend trend — a single inline-SVG polyline, no chart library. */
function Sparkline({ points }: { points: number[] }) {
  const width = 240
  const height = 40
  const max = Math.max(...points)
  const step = points.length > 1 ? width / (points.length - 1) : 0
  const coords = points
    .map((p, i) => {
      const x = i * step
      const y = max > 0 ? height - (p / max) * height : height
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      className="h-10 w-full text-violet-400"
      role="img"
      aria-label="Daily AI spend trend"
    >
      <polyline
        points={coords}
        fill="none"
        stroke="currentColor"
        strokeWidth={2}
        strokeLinejoin="round"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  )
}

function EmptyLine({ text }: { text: string }) {
  return <p className="text-sm text-slate-500">{text}</p>
}

function Dot({ ok }: { ok: boolean }) {
  return (
    <span
      className={`inline-block h-2.5 w-2.5 rounded-full ${ok ? 'bg-emerald-400' : 'bg-red-400'}`}
    />
  )
}
