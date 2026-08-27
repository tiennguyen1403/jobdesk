import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { listSavedSearches, savedSearchesQueryKey } from '../lib/api/savedSearches'
import UpworkPanel from '../components/sources/UpworkPanel'
import SavedSearchForm from '../components/sources/SavedSearchForm'
import SavedSearchCard from '../components/sources/SavedSearchCard'

export default function Sources() {
  const [showForm, setShowForm] = useState(false)

  const { data: searches, isLoading, isError, isFetching } = useQuery({
    queryKey: savedSearchesQueryKey(),
    queryFn: () => listSavedSearches(),
  })

  return (
    <div className="space-y-10">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Sources</h1>
        <p className="text-slate-400">
          Connect Upwork and manage the saved searches the poller runs. JobDesk only finds
          and tracks work — it never applies for you.
        </p>
      </div>

      <UpworkPanel />

      <section className="space-y-4">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold">Saved searches</h2>
            <p className="text-sm text-slate-400">
              Part-time-scoped queries the scheduler polls. Run one now to ingest immediately.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setShowForm((v) => !v)}
            className="shrink-0 rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-slate-950 transition-colors hover:bg-emerald-400"
          >
            {showForm ? 'Close' : '+ New search'}
          </button>
        </div>

        {showForm && <SavedSearchForm onDone={() => setShowForm(false)} />}

        {isLoading ? (
          <p className="text-slate-400">Loading saved searches…</p>
        ) : isError ? (
          <p className="text-red-400">
            Could not load saved searches. Make sure the backend is running (docker compose up).
          </p>
        ) : !searches || searches.length === 0 ? (
          <div className="rounded-xl border border-dashed border-slate-800 bg-slate-900/40 p-10 text-center">
            <p className="text-slate-300">No saved searches yet.</p>
            <p className="mt-1 text-sm text-slate-500">
              Create one to have the poller pull part-time gigs on a schedule.
            </p>
          </div>
        ) : (
          <>
            <p className="text-xs text-slate-500">
              {searches.length} search{searches.length === 1 ? '' : 'es'}
              {isFetching && ' · refreshing…'}
            </p>
            <ul className="space-y-4">
              {searches.map((s) => (
                <li key={s.id}>
                  <SavedSearchCard search={s} />
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
    </div>
  )
}
