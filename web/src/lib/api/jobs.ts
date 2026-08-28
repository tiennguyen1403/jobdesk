// Jobs API client — one file per resource (issue #22) so sibling clients under
// lib/api/ (e.g. the pipeline client from #5) never collide on merge. Kept
// intentionally self-contained: types mirror the backend job schema
// (api/app/schemas/job.py) and the calls speak the real /api/jobs contract.

// Type-only import (erased at build time, so no runtime import cycle): the
// promote action below returns the board card the backend hands back.
import type { ApplicationCard } from './applications'

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
  // --- AI match scoring (score_match); null until the job is scored ---
  match_score: number | null
  match_reasons: string[] | null
  match_part_time_fit: boolean | null
  match_scored_at: string | null
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
  /** Exact-match a single workload (a precise filter). */
  workload?: Workload
  /**
   * Part-time scope lens: keep jobs that are not full-time — part_time OR an
   * unspecified workload. This is what the "Part-time only" toggle sends, so a
   * provider that reports no workload (e.g. Freelancer) is not hidden.
   */
  exclude_full_time?: boolean
  max_weekly_hours?: number
  budget_type?: BudgetType
  q?: string
  limit?: number
  offset?: number
}

function buildQuery(filters: JobFilters): string {
  const params = new URLSearchParams()
  if (filters.workload) params.set('workload', filters.workload)
  if (filters.exclude_full_time) params.set('exclude_full_time', 'true')
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

/** Extract FastAPI's ``{"detail": "..."}`` message, or a status-coded fallback. */
async function readError(res: Response, fallback: string): Promise<string> {
  try {
    const body = await res.json()
    if (body && typeof body.detail === 'string') return body.detail
  } catch {
    // Body wasn't JSON — fall through to the generic message.
  }
  return `${fallback} (${res.status})`
}

/** GET /api/jobs/{id} — one job with its persisted match score. */
export async function getJob(id: number): Promise<Job> {
  const res = await fetch(`${API_BASE}/api/jobs/${id}`)
  if (!res.ok) throw new Error(await readError(res, 'Failed to load job'))
  return res.json()
}

/** Stable React Query key for a single job (the Studio's job feed). */
export const jobQueryKey = (id: number) => ['job', id] as const

/**
 * POST /api/jobs/{id}/application — open a pipeline card for an ingested job
 * that has none yet (the Inbox → pipeline "promote" step). Jobs added by hand
 * already start with a card; this covers postings from other providers (capture,
 * Upwork) that arrive without one. The card enters at 'saved' — JobDesk never
 * auto-applies. 409 if the job is already in the pipeline.
 */
export async function createApplicationForJob(jobId: number): Promise<ApplicationCard> {
  const res = await fetch(`${API_BASE}/api/jobs/${jobId}/application`, { method: 'POST' })
  if (!res.ok) throw new Error(await readError(res, 'Failed to add job to pipeline'))
  return res.json()
}

// --- Phase 2 AI actions (mirror api/app/routers/jobs.py) ---------------------
// Each POST runs a Claude feature and returns the saved result plus the call's
// accounting (model / cost / run_id). JobDesk never auto-applies: tailor-cv and
// draft-proposal only produce editable drafts the user copies out manually.

/** The score_match result for a job (mirrors ScoreMatchResponse). */
export interface ScoreMatchResult {
  job_id: number
  score: number // 0–100, higher = better evenings-and-weekends fit
  reasons: string[]
  part_time_fit: boolean
  model: string
  cost_usd: number
  run_id: number
}

/** The tailor_cv result: the saved tailored CV (mirrors TailorCvResponse). */
export interface TailorCvResult {
  job_id: number
  cv_id: number
  base_cv_id: number
  label: string
  content: string // the tailored CV, as structured markdown
  model: string
  cost_usd: number
  run_id: number
}

/** The draft_proposal result: the saved proposal (mirrors DraftProposalResponse). */
export interface DraftProposalResult {
  job_id: number
  proposal_id: number
  cv_id: number | null
  content: string // the proposal draft, as markdown
  model: string
  cost_usd: number
  run_id: number
}

/** POST /api/jobs/{id}/score-match — (re)score the part-time fit; persists it on the job. */
export async function scoreMatch(id: number): Promise<ScoreMatchResult> {
  const res = await fetch(`${API_BASE}/api/jobs/${id}/score-match`, { method: 'POST' })
  if (!res.ok) throw new Error(await readError(res, 'Failed to score match'))
  return res.json()
}

/** The score-unscored batch summary (mirrors ScoreUnscoredResponse). */
export interface ScoreUnscoredResult {
  scored: number // jobs scored successfully this run
  failed: number // jobs whose AI call failed (counted; the batch continued)
  remaining_unscored: number // jobs still without a score after this run
  total_cost_usd: number
  run_ids: number[]
}

/**
 * POST /api/jobs/score-unscored — score the newest never-scored jobs (match_score
 * IS NULL) in one run, up to `limit`. Each job is a paid Claude call, so callers
 * confirm first and the limit caps the spend.
 */
export async function scoreUnscored(limit?: number): Promise<ScoreUnscoredResult> {
  const qs = limit != null ? `?limit=${limit}` : ''
  const res = await fetch(`${API_BASE}/api/jobs/score-unscored${qs}`, { method: 'POST' })
  if (!res.ok) throw new Error(await readError(res, 'Failed to score unscored jobs'))
  return res.json()
}

/** POST /api/jobs/{id}/tailor-cv — tailor the base CV to the job; saves a new tailored cv row. */
export async function tailorCv(id: number, baseCvId?: number | null): Promise<TailorCvResult> {
  const res = await fetch(`${API_BASE}/api/jobs/${id}/tailor-cv`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(baseCvId != null ? { base_cv_id: baseCvId } : {}),
  })
  if (!res.ok) throw new Error(await readError(res, 'Failed to tailor CV'))
  return res.json()
}

/** POST /api/jobs/{id}/draft-proposal — draft a proposal for the job; saves a new proposal row. */
export async function draftProposal(id: number, cvId?: number | null): Promise<DraftProposalResult> {
  const res = await fetch(`${API_BASE}/api/jobs/${id}/draft-proposal`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(cvId != null ? { cv_id: cvId } : {}),
  })
  if (!res.ok) throw new Error(await readError(res, 'Failed to draft proposal'))
  return res.json()
}
