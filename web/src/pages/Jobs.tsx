import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { jobsQueryKey, listJobs, type JobFilters as ApiJobFilters } from '../lib/api/jobs'
import JobCard from '../components/jobs/JobCard'
import JobFilters, { type JobFiltersValue } from '../components/jobs/JobFilters'
import AddJobForm from '../components/jobs/AddJobForm'

/** Delay a fast-changing value so text search doesn't fire a request per keystroke. */
function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delayMs)
    return () => clearTimeout(id)
  }, [value, delayMs])
  return debounced
}

const INITIAL_FILTERS: JobFiltersValue = {
  partTime: true, // scope guardrail: start on the part-time lens
  maxWeeklyHours: '',
  budgetType: '',
  search: '',
}

/** Map the UI filter state to the backend query params. */
function toApiFilters(f: JobFiltersValue, debouncedSearch: string): ApiJobFilters {
  const maxHours = Number(f.maxWeeklyHours)
  return {
    workload: f.partTime ? 'part_time' : undefined,
    max_weekly_hours:
      f.maxWeeklyHours.trim() !== '' && !Number.isNaN(maxHours) ? maxHours : undefined,
    budget_type: f.budgetType || undefined,
    q: debouncedSearch.trim() || undefined,
  }
}

export default function Jobs() {
  const [filters, setFilters] = useState<JobFiltersValue>(INITIAL_FILTERS)
  const [showForm, setShowForm] = useState(false)
  const debouncedSearch = useDebouncedValue(filters.search, 300)

  const apiFilters = toApiFilters(filters, debouncedSearch)
  const { data: jobs, isLoading, isError, isFetching } = useQuery({
    queryKey: jobsQueryKey(apiFilters),
    queryFn: () => listJobs(apiFilters),
  })

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Jobs</h1>
          <p className="text-slate-400">
            Add and browse postings — filtered to part-time / hourly / project work.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowForm((v) => !v)}
          className="shrink-0 rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-slate-950 transition-colors hover:bg-emerald-400"
        >
          {showForm ? 'Close' : '+ Add job'}
        </button>
      </div>

      {showForm && <AddJobForm onCreated={() => setShowForm(false)} />}

      <JobFilters
        value={filters}
        onChange={(patch) => setFilters((f) => ({ ...f, ...patch }))}
      />

      {isLoading ? (
        <p className="text-slate-400">Loading jobs…</p>
      ) : isError ? (
        <p className="text-red-400">
          Could not load jobs. Make sure the backend is running (docker compose up).
        </p>
      ) : !jobs || jobs.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-800 bg-slate-900/40 p-10 text-center">
          <p className="text-slate-300">No jobs match these filters.</p>
          <p className="mt-1 text-sm text-slate-500">
            Add one by hand, or loosen the filters (e.g. turn off “Part-time only”).
          </p>
        </div>
      ) : (
        <>
          <p className="text-xs text-slate-500">
            {jobs.length} job{jobs.length === 1 ? '' : 's'}
            {isFetching && ' · refreshing…'}
          </p>
          <ul className="space-y-4">
            {jobs.map((job) => (
              <li key={job.id}>
                <JobCard job={job} />
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}
