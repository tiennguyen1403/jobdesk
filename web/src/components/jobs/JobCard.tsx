import { Link } from 'react-router-dom'
import type { Job } from '../../lib/api/jobs'

/** Currency-aware budget label, e.g. "$30–$50/hr" or "$500 fixed". */
function formatBudget(job: Job): string {
  const money = (n: number) =>
    new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency: job.currency || 'USD',
      maximumFractionDigits: 0,
    }).format(n)

  const { budget_min: min, budget_max: max, budget_type: type } = job
  const suffix = type === 'hourly' ? '/hr' : ' fixed'

  let amount: string
  if (min != null && max != null) amount = min === max ? money(min) : `${money(min)}–${money(max)}`
  else if (min != null) amount = `${money(min)}+`
  else if (max != null) amount = `up to ${money(max)}`
  else return type === 'hourly' ? 'Hourly rate n/a' : 'Budget n/a'

  return `${amount}${suffix}`
}

/** 'one_to_three_months' -> 'one to three months'. */
function humanize(value: string): string {
  return value.replace(/_/g, ' ')
}

// Source badge — makes an ingested job legible at a glance (issue #59). Keyed by
// the provider's `source`; an unknown source falls back to a neutral pill so a
// future platform still renders without a code change.
const SOURCE_LABELS: Record<string, string> = {
  manual: 'Manual',
  capture: 'Capture',
  upwork: 'Upwork',
}

const SOURCE_STYLES: Record<string, string> = {
  manual: 'bg-slate-800 text-slate-300 ring-slate-700',
  capture: 'bg-sky-500/10 text-sky-300 ring-sky-500/30',
  upwork: 'bg-emerald-500/10 text-emerald-300 ring-emerald-500/30',
}

const SOURCE_FALLBACK_STYLE = 'bg-slate-800 text-slate-300 ring-slate-700'

function formatPosted(iso: string | null): string | null {
  if (!iso) return null
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return null
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

export default function JobCard({
  job,
  onAddToPipeline,
  isPromoting = false,
}: {
  job: Job
  /** Promote an ingested job with no card into the Kanban at 'saved'. */
  onAddToPipeline?: () => void
  /** True while this job's promote request is in flight. */
  isPromoting?: boolean
}) {
  const posted = formatPosted(job.posted_at)
  const partTime = job.workload === 'part_time'
  const sourceLabel = SOURCE_LABELS[job.source] ?? job.source
  const sourceStyle = SOURCE_STYLES[job.source] ?? SOURCE_FALLBACK_STYLE

  return (
    <article className="rounded-xl border border-slate-800 bg-slate-900 p-5 transition-colors hover:border-slate-700">
      <div className="flex items-start justify-between gap-4">
        <h3 className="text-base font-semibold text-slate-100">
          <a
            href={job.url}
            target="_blank"
            rel="noreferrer"
            className="hover:text-emerald-300 hover:underline"
          >
            {job.title}
          </a>
        </h3>
        <span className="shrink-0 whitespace-nowrap font-mono text-sm text-emerald-300">
          {formatBudget(job)}
        </span>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
        {job.workload && (
          <span
            className={`rounded-full px-2.5 py-1 font-medium ${
              partTime
                ? 'bg-emerald-500/10 text-emerald-300 ring-1 ring-emerald-500/30'
                : 'bg-amber-500/10 text-amber-300 ring-1 ring-amber-500/30'
            }`}
          >
            {humanize(job.workload)}
          </span>
        )}
        {job.weekly_hours != null && (
          <span className="rounded-full bg-slate-800 px-2.5 py-1 text-slate-300">
            ~{job.weekly_hours}h/wk
          </span>
        )}
        {job.duration && (
          <span className="rounded-full bg-slate-800 px-2.5 py-1 text-slate-300">
            {humanize(job.duration)}
          </span>
        )}
        {job.client_country && (
          <span className="rounded-full bg-slate-800 px-2.5 py-1 text-slate-300">
            {job.client_country}
          </span>
        )}
      </div>

      {job.description && (
        <p className="mt-3 line-clamp-3 text-sm text-slate-400">{job.description}</p>
      )}

      {job.skills.length > 0 && (
        <ul className="mt-3 flex flex-wrap gap-1.5">
          {job.skills.map((skill) => (
            <li
              key={skill}
              className="rounded bg-slate-800/80 px-2 py-0.5 text-xs text-slate-300"
            >
              {skill}
            </li>
          ))}
        </ul>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-2 text-xs">
        <span
          className={`rounded-full px-2 py-0.5 font-medium ring-1 ${sourceStyle}`}
          title={`Source: ${sourceLabel}`}
        >
          {sourceLabel}
        </span>
        {posted && <span className="text-slate-500">posted {posted}</span>}
        {job.application && (
          <span className="capitalize text-slate-400">{job.application.status}</span>
        )}
        {job.match_score != null && (
          <span className="font-mono text-emerald-300/80">match {job.match_score}</span>
        )}
        <div className="ml-auto flex items-center gap-2">
          {!job.application && (
            <button
              type="button"
              onClick={onAddToPipeline}
              disabled={isPromoting}
              className="rounded-md border border-emerald-600/50 px-2.5 py-1 font-medium text-emerald-300 transition-colors hover:border-emerald-500 hover:bg-emerald-500/10 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isPromoting ? 'Adding…' : '+ Add to pipeline'}
            </button>
          )}
          <Link
            to={`/studio/${job.id}`}
            className="rounded-md border border-slate-700 px-2.5 py-1 font-medium text-slate-200 transition-colors hover:border-emerald-500/60 hover:text-emerald-300"
          >
            Studio →
          </Link>
        </div>
      </div>
    </article>
  )
}
