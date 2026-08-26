// Jobs API client — one file per resource (issue #22) so sibling clients under
// lib/api/ (e.g. the pipeline client from #5) never collide on merge. Kept
// intentionally self-contained: types mirror the backend job schema
// (api/app/schemas/job.py) and the calls speak the real /api/jobs contract.

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

export type BudgetType = 'hourly' | 'fixed'
export type Workload = 'part_time' | 'full_time'
export type ApplicationStatus = 'saved' | 'applied' | 'interviewing' | 'offer' | 'rejected'

/** The 1–1 pipeline card embedded in a job (mirrors ApplicationRead). */
export interface Application {
  id: number
  status: ApplicationStatus
  notes: string | null
  applied_at: string | null
  created_at: string
  updated_at: string
}

/** A persisted job as returned by GET /api/jobs (mirrors JobRead). */
export interface Job {
  id: number
  source: string
  external_id: string | null
  url: string
  title: string
  description: string
  budget_type: BudgetType
  budget_min: number | null
  budget_max: number | null
  currency: string
  workload: Workload | null
  weekly_hours: number | null
  duration: string | null
  skills: string[]
  client_country: string | null
  posted_at: string | null
  created_at: string
  updated_at: string
  application: Application | null
}

/** Payload for POST /api/jobs (mirrors JobCreate). Source is always 'manual'. */
export interface JobCreate {
  url: string
  title: string
  description?: string
  external_id?: string | null
  budget_type?: BudgetType
  budget_min?: number | null
  budget_max?: number | null
  currency?: string
  workload?: Workload | null
  weekly_hours?: number | null
  duration?: string | null
  skills?: string[]
  client_country?: string | null
  posted_at?: string | null
}

/** Jobs-list filters, mirroring the backend query params (the part-time scope). */
export interface JobFilters {
  /** Scope guardrail: pass 'part_time' to hide full-time postings. */
  workload?: Workload
  max_weekly_hours?: number
  budget_type?: BudgetType
  q?: string
  limit?: number
  offset?: number
}

function buildQuery(filters: JobFilters): string {
  const params = new URLSearchParams()
  if (filters.workload) params.set('workload', filters.workload)
  if (filters.max_weekly_hours != null)
    params.set('max_weekly_hours', String(filters.max_weekly_hours))
  if (filters.budget_type) params.set('budget_type', filters.budget_type)
  if (filters.q) params.set('q', filters.q)
  if (filters.limit != null) params.set('limit', String(filters.limit))
  if (filters.offset != null) params.set('offset', String(filters.offset))
  const qs = params.toString()
  return qs ? `?${qs}` : ''
}

/** GET /api/jobs — newest first, narrowed by the part-time scope filters. */
export async function listJobs(filters: JobFilters = {}): Promise<Job[]> {
  const res = await fetch(`${API_BASE}/api/jobs${buildQuery(filters)}`)
  if (!res.ok) throw new Error(`Failed to load jobs (${res.status})`)
  return res.json()
}

/** POST /api/jobs — add a hand-entered job; it enters the pipeline at 'saved'. */
export async function createJob(payload: JobCreate): Promise<Job> {
  const res = await fetch(`${API_BASE}/api/jobs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new Error(`Failed to add job (${res.status})${detail ? `: ${detail}` : ''}`)
  }
  return res.json()
}

/**
 * Stable React Query key for the jobs list. Including the filters makes each
 * filter combination its own cache entry; a bare ['jobs'] prefix lets mutations
 * invalidate them all at once.
 */
export const jobsQueryKey = (filters: JobFilters = {}) => ['jobs', filters] as const
