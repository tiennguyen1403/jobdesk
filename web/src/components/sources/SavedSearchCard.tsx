import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  deleteSavedSearch,
  runSavedSearch,
  updateSavedSearch,
  type SavedSearch,
  type SavedSearchRunResult,
  type SearchQuery,
} from '../../lib/api/savedSearches'
import SavedSearchForm from './SavedSearchForm'

/** Localised timestamp; 'never' for a search that has not been polled yet. */
function formatWhen(iso: string | null): string {
  if (!iso) return 'never'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}

/** One-line summary of what a search looks for (keywords + part-time constraints). */
function summarizeQuery(q: SearchQuery): string {
  const parts: string[] = [q.keywords.trim() ? `“${q.keywords.trim()}”` : 'any keywords']
  if (q.category) parts.push(q.category)
  if (q.workload) parts.push(q.workload === 'part_time' ? 'part-time' : 'full-time')
  if (q.max_weekly_hours != null) parts.push(`≤ ${q.max_weekly_hours} h/wk`)
  return parts.join(' · ')
}

const actionClass =
  'rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-medium text-slate-300 ' +
  'transition-colors hover:border-slate-600 hover:text-slate-100 disabled:cursor-not-allowed disabled:opacity-50'

export default function SavedSearchCard({ search }: { search: SavedSearch }) {
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [confirmingDelete, setConfirmingDelete] = useState(false)

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['saved-searches'] })

  const run = useMutation({
    mutationFn: () => runSavedSearch(search.id),
    onSuccess: () => {
      invalidate() // the run stamps last_polled_at
      queryClient.invalidateQueries({ queryKey: ['jobs'] }) // ingested jobs land in the Inbox
    },
  })

  const toggle = useMutation({
    mutationFn: () => updateSavedSearch(search.id, { enabled: !search.enabled }),
    onSuccess: invalidate,
  })

  const remove = useMutation({
    mutationFn: () => deleteSavedSearch(search.id),
    onSuccess: invalidate,
  })

  if (editing) {
    return <SavedSearchForm initial={search} onDone={() => setEditing(false)} />
  }

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-medium text-slate-100">{search.name}</h3>
            <span className="rounded-full bg-slate-800 px-2 py-0.5 font-mono text-xs text-slate-400">
              {search.provider}
            </span>
            <StatusPill enabled={search.enabled} />
          </div>
          <p className="mt-1 text-sm text-slate-400">{summarizeQuery(search.query)}</p>
          <p className="mt-1 text-xs text-slate-500">
            Last polled: {formatWhen(search.last_polled_at)}
          </p>
        </div>

        <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
          <button
            type="button"
            onClick={() => run.mutate()}
            disabled={run.isPending}
            className="rounded-lg bg-emerald-500 px-3 py-1.5 text-xs font-semibold text-slate-950 transition-colors hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {run.isPending ? 'Running…' : 'Run now'}
          </button>
          <button
            type="button"
            onClick={() => toggle.mutate()}
            disabled={toggle.isPending}
            className={actionClass}
          >
            {search.enabled ? 'Disable' : 'Enable'}
          </button>
          <button type="button" onClick={() => setEditing(true)} className={actionClass}>
            Edit
          </button>
          {confirmingDelete ? (
            <>
              <button
                type="button"
                onClick={() => remove.mutate()}
                disabled={remove.isPending}
                className="rounded-lg border border-rose-500/40 px-3 py-1.5 text-xs font-medium text-rose-400 transition-colors hover:border-rose-500/70 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {remove.isPending ? 'Deleting…' : 'Confirm delete'}
              </button>
              <button
                type="button"
                onClick={() => setConfirmingDelete(false)}
                className="px-2 py-1.5 text-xs text-slate-400 hover:text-slate-200"
              >
                Cancel
              </button>
            </>
          ) : (
            <button
              type="button"
              onClick={() => setConfirmingDelete(true)}
              className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-medium text-slate-400 transition-colors hover:border-rose-500/50 hover:text-rose-400"
            >
              Delete
            </button>
          )}
        </div>
      </div>

      {run.isSuccess && run.data && <RunResult result={run.data} />}
      {run.isError && (
        <p className="mt-3 text-sm text-red-400">
          {run.error instanceof Error ? run.error.message : 'Run failed.'}
        </p>
      )}
      {(toggle.isError || remove.isError) && (
        <p className="mt-3 text-sm text-red-400">That action failed. Try refreshing.</p>
      )}
    </div>
  )
}

function StatusPill({ enabled }: { enabled: boolean }) {
  return enabled ? (
    <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-xs font-medium text-emerald-400">
      Enabled
    </span>
  ) : (
    <span className="rounded-full bg-slate-700/40 px-2 py-0.5 text-xs font-medium text-slate-300">
      Disabled
    </span>
  )
}

function RunResult({ result }: { result: SavedSearchRunResult }) {
  return (
    <div className="mt-4 rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3 text-sm">
      <p className="text-slate-200">
        <span className="font-semibold text-emerald-400">{result.created}</span> new ·{' '}
        <span className="font-semibold text-sky-400">{result.updated}</span> updated ·{' '}
        <span className="font-semibold text-slate-400">{result.skipped}</span> skipped
      </p>
      <p className="mt-1 text-xs text-slate-500">
        {result.job_ids.length} job{result.job_ids.length === 1 ? '' : 's'} touched · polled{' '}
        {formatWhen(result.last_polled_at)}
      </p>
    </div>
  )
}
