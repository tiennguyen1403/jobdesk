// Dashboard analytics API client — its own module under lib/api/ (like jobs.ts /
// aiRuns.ts) so sibling clients never collide on merge. Types mirror the backend
// summary schema (api/app/schemas/analytics.py, AnalyticsSummary); the call
// speaks the real /api/analytics/summary contract. This is a single read-only
// rollup of JobDesk's own tables (job / application / ai_run) — the Dashboard
// reads it and never writes back.

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

/** Jobs the tracker holds, split by the provider that supplied them (mirrors JobsAnalytics). */
export interface JobsAnalytics {
  total: number
  /** Always carries the four canonical sources (manual / capture / upwork / freelancer), zero when none. */
  by_source: Record<string, number>
}

/** Scored jobs bucketed by AI match score, 0–100 inclusive (mirrors MatchBands). */
export interface MatchBands {
  low: number // 0–39
  medium: number // 40–69
  high: number // 70–100
}

/** AI match-scoring coverage + distribution across all jobs (mirrors MatchAnalytics). */
export interface MatchAnalytics {
  /** scored + unscored === jobs.total (NULL match_score means "not scored yet"). */
  scored: number
  unscored: number
  /** Jobs the scorer flagged as fitting the evenings-and-weekends scope. */
  part_time_fit: number
  bands: MatchBands
}

/** The application funnel as current counts per pipeline stage (mirrors PipelineAnalytics). */
export interface PipelineAnalytics {
  total: number
  by_status: Record<string, number>
  /** Fraction of cards past `saved` (i.e. applied on the platform); 0.0 when empty. */
  applied_conversion: number
}

/** AI spend + usage rolled up for one feature, e.g. `score_match` (mirrors AiFeatureCost). */
export interface AiFeatureCost {
  feature: string
  cost_usd: number
  input_tokens: number
  output_tokens: number
  runs: number
}

/** AI spend + usage for a single UTC calendar day in the window (mirrors AiDailySpend). */
export interface AiDailySpend {
  /** ISO date (YYYY-MM-DD). */
  date: string
  cost_usd: number
  input_tokens: number
  output_tokens: number
  runs: number
}

/** Claude usage ledger: lifetime totals, a per-feature split, and a recent daily series (mirrors AiAnalytics). */
export interface AiAnalytics {
  total_cost_usd: number
  input_tokens: number
  output_tokens: number
  by_feature: AiFeatureCost[]
  /** Length of the trailing window the `recent` series covers. */
  days: number
  /** Sparse — only days that actually had runs, oldest first. */
  recent: AiDailySpend[]
}

/** Everything the Dashboard renders in one payload (mirrors AnalyticsSummary). */
export interface AnalyticsSummary {
  jobs: JobsAnalytics
  match: MatchAnalytics
  pipeline: PipelineAnalytics
  ai: AiAnalytics
}

/**
 * GET /api/analytics/summary — the one payload the Dashboard rolls up. `days`
 * sets the trailing window for the AI daily-spend series; the backend defaults
 * to 30 and clamps to 1–365, so we only send it when a caller overrides it.
 */
export async function getAnalyticsSummary(days?: number): Promise<AnalyticsSummary> {
  const qs = days != null ? `?days=${days}` : ''
  const res = await fetch(`${API_BASE}/api/analytics/summary${qs}`)
  if (!res.ok) throw new Error(`Failed to load analytics summary (${res.status})`)
  return res.json()
}

/**
 * Stable React Query key for the summary. Keyed by the window so a different
 * `days` is its own cache entry; a bare ['analytics-summary'] prefix still lets a
 * future refresh invalidate every window at once.
 */
export const analyticsSummaryQueryKey = (days?: number) => ['analytics-summary', days] as const
