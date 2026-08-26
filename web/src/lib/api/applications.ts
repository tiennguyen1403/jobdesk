// Applications (pipeline) API client — its own module under lib/api/ (issue #23)
// so it never collides with jobs.ts on merge. Types mirror the backend
// application schema (api/app/schemas/application.py); the calls speak the real
// /api/applications contract the Kanban board is built on.

import type { ApplicationStatus, BudgetType, Workload } from './jobs'

// Re-exported so board components import the stage type from this module, keeping
// the pipeline client self-contained as the one source of truth for its shape.
export type { ApplicationStatus }

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

/**
 * The pipeline stages in board order — one Kanban column each. Fixed to the
 * Phase-1 enum (api/app/models/application.py); the board never invents stages.
 */
export const APPLICATION_STAGES = [
  'saved',
  'applied',
  'interviewing',
  'offer',
  'rejected',
] as const satisfies readonly ApplicationStatus[]

/** Column titles, keyed by stage. */
export const STAGE_LABELS: Record<ApplicationStatus, string> = {
  saved: 'Saved',
  applied: 'Applied',
  interviewing: 'Interviewing',
  offer: 'Offer',
  rejected: 'Rejected',
}

/** Compact job facts embedded in a card (mirrors backend JobSummary). */
export interface JobSummary {
  id: number
  source: string
  title: string
  url: string
  budget_type: BudgetType
  budget_min: number | null
  budget_max: number | null
  currency: string
  workload: Workload | null
  weekly_hours: number | null
  duration: string | null
}

/** A board card: the pipeline application plus its job summary (mirrors ApplicationCard). */
export interface ApplicationCard {
  id: number
  status: ApplicationStatus
  notes: string | null
  applied_at: string | null
  created_at: string
  updated_at: string
  job: JobSummary
}

/** Partial update for a card (mirrors ApplicationUpdate); only present keys change. */
export interface ApplicationUpdate {
  status?: ApplicationStatus
  notes?: string | null
  applied_at?: string | null
}

/** Optional board filters, mirroring the backend query params. */
export interface ApplicationFilters {
  status?: ApplicationStatus
  limit?: number
  offset?: number
}

function buildQuery(filters: ApplicationFilters): string {
  const params = new URLSearchParams()
  if (filters.status) params.set('status', filters.status)
  if (filters.limit != null) params.set('limit', String(filters.limit))
  if (filters.offset != null) params.set('offset', String(filters.offset))
  const qs = params.toString()
  return qs ? `?${qs}` : ''
}

/** GET /api/applications — pipeline cards, newest first, each embedding its job. */
export async function listApplications(
  filters: ApplicationFilters = {},
): Promise<ApplicationCard[]> {
  const res = await fetch(`${API_BASE}/api/applications${buildQuery(filters)}`)
  if (!res.ok) throw new Error(`Failed to load applications (${res.status})`)
  return res.json()
}

/**
 * PATCH /api/applications/{id} — move a card between stages or edit its notes.
 * Tracking-only: advancing to 'applied' just records a manual apply on the
 * platform; JobDesk never submits anything itself.
 */
export async function updateApplication(
  id: number,
  patch: ApplicationUpdate,
): Promise<ApplicationCard> {
  const res = await fetch(`${API_BASE}/api/applications/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  })
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new Error(`Failed to update card (${res.status})${detail ? `: ${detail}` : ''}`)
  }
  return res.json()
}

/**
 * Stable React Query key for the board feed. A bare ['applications'] prefix lets
 * a move / notes mutation invalidate every cached filter at once.
 */
export const applicationsQueryKey = (filters: ApplicationFilters = {}) =>
  ['applications', filters] as const
