import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  APPLICATION_STAGES,
  STAGE_LABELS,
  type ApplicationCard,
  type ApplicationStatus,
  type JobSummary,
} from '../../lib/api/applications'

/** Currency-aware budget label, e.g. "$30–$50/hr" or "$500 fixed". */
function formatBudget(job: JobSummary): string {
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
  else return type === 'hourly' ? 'Rate n/a' : 'Budget n/a'

  return `${amount}${suffix}`
}

/** 'one_to_three_months' -> 'one to three months'. */
function humanize(value: string): string {
  return value.replace(/_/g, ' ')
}

function formatDate(iso: string | null): string | null {
  if (!iso) return null
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return null
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

interface Props {
  card: ApplicationCard
  /** Move the card to another stage (drag-and-drop's accessible fallback). */
  onMove: (status: ApplicationStatus) => void
  /** Persist edited notes (empty string clears them). */
  onSaveNotes: (notes: string) => void
  /** Dim + disable while its PATCH is in flight. */
  isUpdating?: boolean
  onDragStart?: () => void
  onDragEnd?: () => void
}

export default function PipelineCard({
  card,
  onMove,
  onSaveNotes,
  isUpdating = false,
  onDragStart,
  onDragEnd,
}: Props) {
  const { job } = card
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(card.notes ?? '')
  const partTime = job.workload === 'part_time'
  const applied = formatDate(card.applied_at)

  const startEdit = () => {
    setDraft(card.notes ?? '')
    setEditing(true)
  }
  const save = () => {
    onSaveNotes(draft.trim())
    setEditing(false)
  }

  return (
    <article
      draggable
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      className={`cursor-grab rounded-lg border border-slate-800 bg-slate-900 p-3 transition-colors hover:border-slate-700 active:cursor-grabbing ${
        isUpdating ? 'opacity-60' : ''
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-sm font-semibold leading-snug text-slate-100">
          <a
            href={job.url}
            target="_blank"
            rel="noreferrer"
            className="hover:text-emerald-300 hover:underline"
          >
            {job.title}
          </a>
        </h3>
        <span className="shrink-0 whitespace-nowrap font-mono text-xs text-emerald-300">
          {formatBudget(job)}
        </span>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[11px]">
        {job.workload && (
          <span
            className={`rounded-full px-2 py-0.5 font-medium ${
              partTime
                ? 'bg-emerald-500/10 text-emerald-300 ring-1 ring-emerald-500/30'
                : 'bg-amber-500/10 text-amber-300 ring-1 ring-amber-500/30'
            }`}
          >
            {humanize(job.workload)}
          </span>
        )}
        {job.weekly_hours != null && (
          <span className="rounded-full bg-slate-800 px-2 py-0.5 text-slate-300">
            ~{job.weekly_hours}h/wk
          </span>
        )}
        {job.duration && (
          <span className="rounded-full bg-slate-800 px-2 py-0.5 text-slate-300">
            {humanize(job.duration)}
          </span>
        )}
      </div>

      <div className="mt-3">
        {editing ? (
          <div className="space-y-2">
            <textarea
              aria-label="Card notes"
              rows={3}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Notes to self — why it fits evenings, contact, next step…"
              className="w-full rounded-md border border-slate-800 bg-slate-950 px-2 py-1.5 text-xs text-slate-100 placeholder:text-slate-600 focus:border-slate-600 focus:outline-none focus:ring-1 focus:ring-slate-600"
            />
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={save}
                className="rounded-md bg-emerald-500 px-2.5 py-1 text-xs font-semibold text-slate-950 transition-colors hover:bg-emerald-400"
              >
                Save
              </button>
              <button
                type="button"
                onClick={() => setEditing(false)}
                className="rounded-md px-2.5 py-1 text-xs text-slate-400 hover:text-slate-200"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : card.notes ? (
          <button
            type="button"
            onClick={startEdit}
            className="block w-full whitespace-pre-wrap rounded-md bg-slate-800/50 px-2 py-1.5 text-left text-xs text-slate-300 transition-colors hover:bg-slate-800"
          >
            {card.notes}
          </button>
        ) : (
          <button
            type="button"
            onClick={startEdit}
            className="text-xs text-slate-500 transition-colors hover:text-slate-300"
          >
            + Add notes
          </button>
        )}
      </div>

      <div className="mt-3 flex items-center justify-between gap-2">
        <label className="flex items-center gap-1.5 text-[11px] text-slate-500">
          Move to
          <select
            aria-label={`Move "${job.title}" to another stage`}
            value={card.status}
            onChange={(e) => onMove(e.target.value as ApplicationStatus)}
            disabled={isUpdating}
            className="rounded-md border border-slate-800 bg-slate-950 px-1.5 py-1 text-[11px] text-slate-200 focus:border-slate-600 focus:outline-none focus:ring-1 focus:ring-slate-600 disabled:opacity-50"
          >
            {APPLICATION_STAGES.map((s) => (
              <option key={s} value={s}>
                {STAGE_LABELS[s]}
              </option>
            ))}
          </select>
        </label>
        <div className="flex items-center gap-2">
          <Link
            to={`/studio/${job.id}`}
            className="rounded-md border border-slate-800 px-2 py-0.5 text-[11px] font-medium text-slate-300 transition-colors hover:border-emerald-500/60 hover:text-emerald-300"
          >
            Studio
          </Link>
          <span className="font-mono text-[10px] uppercase tracking-wide text-slate-600">
            {job.source}
            {applied && ` · ${applied}`}
          </span>
        </div>
      </div>
    </article>
  )
}
