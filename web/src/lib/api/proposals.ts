// Proposals API client — one file per resource (like jobs.ts / applications.ts).
// Types mirror the backend proposal schema (api/app/schemas/proposal.py); the
// calls speak the real /api/proposals contract. The Studio uses this to load a
// job's latest draft and to persist hand-edits before the user copies it out to
// apply manually — JobDesk never submits a proposal itself.

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

/** A persisted proposal as returned by the API (mirrors ProposalRead). */
export interface Proposal {
  id: number
  job_id: number
  content: string
  created_at: string
  updated_at: string
}

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

/** GET /api/proposals?job_id={id} — the proposals drafted for one job, newest first. */
export async function listProposals(jobId: number): Promise<Proposal[]> {
  const res = await fetch(`${API_BASE}/api/proposals?job_id=${jobId}`)
  if (!res.ok) throw new Error(await readError(res, 'Failed to load proposals'))
  return res.json()
}

/** PATCH /api/proposals/{id} — persist an edit to a proposal's markdown content. */
export async function updateProposal(id: number, content: string): Promise<Proposal> {
  const res = await fetch(`${API_BASE}/api/proposals/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  })
  if (!res.ok) throw new Error(await readError(res, 'Failed to save proposal'))
  return res.json()
}

/** Stable React Query key for a job's proposals. */
export const proposalsQueryKey = (jobId: number) => ['proposals', jobId] as const
