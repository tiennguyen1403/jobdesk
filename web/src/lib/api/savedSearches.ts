// Saved searches API client — its own module under lib/api/ (like jobs.ts /
// applications.ts) so sibling clients never collide on merge. Types mirror the
// backend saved-search schema (api/app/schemas/saved_search.py); the calls speak
// the real /api/saved-searches contract the poller iterates.
//
// Part-time scope is first-class: a search's `query` carries the workload /
// max_weekly_hours constraints so polling only pulls evenings-and-weekends work.
// A saved search only *finds* work — JobDesk never auto-applies.

import type { Workload } from './jobs'

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

/** The typed shape of a saved search's `query` (mirrors SearchQuery). */
export interface SearchQuery {
  keywords: string
  category: string | null
  /** Part-time constraint: 'part_time' keeps the poll within side-gig scope. */
  workload: Workload | null
  /** Part-time constraint: drop postings above this weekly-hours cap. */
  max_weekly_hours: number | null
}

/** A persisted saved search as returned by the API (mirrors SavedSearchRead). */
export interface SavedSearch {
  id: number
  name: string
  provider: string
  query: SearchQuery
  enabled: boolean
  last_polled_at: string | null
  created_at: string
  updated_at: string
}

/** Payload for POST /api/saved-searches (mirrors SavedSearchCreate). */
export interface SavedSearchCreate {
  name: string
  provider?: string
  query?: Partial<SearchQuery>
  enabled?: boolean
}

/**
 * Partial update (mirrors SavedSearchUpdate) — only the keys present change, and
 * `query` is replaced wholesale (not deep-merged) when supplied.
 */
export interface SavedSearchUpdate {
  name?: string
  provider?: string
  query?: Partial<SearchQuery>
  enabled?: boolean
}

/** The ingest summary from one on-demand poll (mirrors SavedSearchRunResult). */
export interface SavedSearchRunResult {
  search_id: number
  provider: string
  created: number
  updated: number
  skipped: number
  job_ids: number[]
  last_polled_at: string | null
}

/** List filters, mirroring the backend query params. */
export interface SavedSearchFilters {
  provider?: string
  enabled?: boolean
  limit?: number
  offset?: number
}

function buildQuery(filters: SavedSearchFilters): string {
  const params = new URLSearchParams()
  if (filters.provider) params.set('provider', filters.provider)
  if (filters.enabled != null) params.set('enabled', String(filters.enabled))
  if (filters.limit != null) params.set('limit', String(filters.limit))
  if (filters.offset != null) params.set('offset', String(filters.offset))
  const qs = params.toString()
  return qs ? `?${qs}` : ''
}

/** Extract FastAPI's `{"detail": "..."}` message, or a status-coded fallback. */
async function readError(res: Response, fallback: string): Promise<string> {
  try {
    const body = await res.json()
    if (body && typeof body.detail === 'string') return body.detail
  } catch {
    // Body wasn't JSON — fall through to the generic message.
  }
  return `${fallback} (${res.status})`
}

/** GET /api/saved-searches — saved searches, newest first. */
export async function listSavedSearches(
  filters: SavedSearchFilters = {},
): Promise<SavedSearch[]> {
  const res = await fetch(`${API_BASE}/api/saved-searches${buildQuery(filters)}`)
  if (!res.ok) throw new Error(await readError(res, 'Failed to load saved searches'))
  return res.json()
}

/** POST /api/saved-searches — create a reusable, part-time-scoped search. */
export async function createSavedSearch(payload: SavedSearchCreate): Promise<SavedSearch> {
  const res = await fetch(`${API_BASE}/api/saved-searches`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) throw new Error(await readError(res, 'Failed to create saved search'))
  return res.json()
}

/** PATCH /api/saved-searches/{id} — edit a search; only the keys present change. */
export async function updateSavedSearch(
  id: number,
  patch: SavedSearchUpdate,
): Promise<SavedSearch> {
  const res = await fetch(`${API_BASE}/api/saved-searches/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  })
  if (!res.ok) throw new Error(await readError(res, 'Failed to update saved search'))
  return res.json()
}

/** DELETE /api/saved-searches/{id} — remove a search so the poller stops iterating it. */
export async function deleteSavedSearch(id: number): Promise<void> {
  const res = await fetch(`${API_BASE}/api/saved-searches/${id}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(await readError(res, 'Failed to delete saved search'))
}

/**
 * POST /api/saved-searches/{id}/run — poll one search now and return the ingest
 * summary. Ingested jobs land in the Inbox; JobDesk never auto-applies. A 503/502
 * (Upwork unconfigured / not connected) or 422 (provider can't be polled) surfaces
 * as a thrown Error carrying the backend's detail message.
 */
export async function runSavedSearch(id: number): Promise<SavedSearchRunResult> {
  const res = await fetch(`${API_BASE}/api/saved-searches/${id}/run`, { method: 'POST' })
  if (!res.ok) throw new Error(await readError(res, 'Failed to run saved search'))
  return res.json()
}

/**
 * Stable React Query key for the saved-searches list. Including the filters makes
 * each combination its own cache entry; a bare ['saved-searches'] prefix lets a
 * mutation invalidate them all at once.
 */
export const savedSearchesQueryKey = (filters: SavedSearchFilters = {}) =>
  ['saved-searches', filters] as const
