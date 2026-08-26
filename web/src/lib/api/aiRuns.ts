// AI runs API client — its own module under lib/api/ (like jobs.ts /
// applications.ts) so sibling clients never collide on merge. Types mirror the
// backend AI-run schema (api/app/schemas/ai.py, AiRunRead); the calls speak the
// real /api/ai/runs contract. This is a read-only cost/usage ledger — every
// Claude call (score_match / tailor_cv / draft_proposal / smoke) logs one row
// here, and the UI only ever reads it back.

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

/** Outcome of a logged AI call — the backend keeps 'success' or 'error'. */
export type AiRunStatus = 'success' | 'error'

/**
 * The AI features that write ledger rows (api/app/routers). Kept as a plain list
 * (not an exhaustive union) so the client keeps working if the backend adds one;
 * the filter dropdown offers these, but any feature string renders fine.
 */
export const KNOWN_AI_FEATURES = [
  'score_match',
  'tailor_cv',
  'draft_proposal',
  'smoke',
] as const

/** One row of the AI cost/usage ledger (mirrors AiRunRead). */
export interface AiRun {
  id: number
  feature: string
  model: string
  status: string
  input_tokens: number
  output_tokens: number
  cost_usd: number
  error: string | null
  job_id: number | null
  created_at: string
}

/** Ledger filters, mirroring the backend query params. */
export interface AiRunFilters {
  feature?: string
  status?: AiRunStatus
  limit?: number
  offset?: number
}

function buildQuery(filters: AiRunFilters): string {
  const params = new URLSearchParams()
  if (filters.feature) params.set('feature', filters.feature)
  if (filters.status) params.set('status', filters.status)
  if (filters.limit != null) params.set('limit', String(filters.limit))
  if (filters.offset != null) params.set('offset', String(filters.offset))
  const qs = params.toString()
  return qs ? `?${qs}` : ''
}

/** GET /api/ai/runs — the AI cost/usage ledger, newest first. */
export async function listAiRuns(filters: AiRunFilters = {}): Promise<AiRun[]> {
  const res = await fetch(`${API_BASE}/api/ai/runs${buildQuery(filters)}`)
  if (!res.ok) throw new Error(`Failed to load AI runs (${res.status})`)
  return res.json()
}

/**
 * Stable React Query key for the ledger. Including the filters makes each filter
 * combination its own cache entry; a bare ['ai-runs'] prefix would let a future
 * mutation invalidate them all at once.
 */
export const aiRunsQueryKey = (filters: AiRunFilters = {}) => ['ai-runs', filters] as const
