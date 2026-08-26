// CVs API client — one file per resource (like jobs.ts / applications.ts) so
// sibling clients never collide on merge. Types mirror the backend CV schema
// (api/app/schemas/cv.py); the calls speak the real /api/cvs contract. The
// Studio uses this to load the CV already tailored for a job and to persist
// hand-edits to it.

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

/** A persisted CV as returned by the API (mirrors CvRead). */
export interface Cv {
  id: number
  label: string
  content: string
  // NULL = base/master CV; set = tailored for that job.
  job_id: number | null
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

/** GET /api/cvs?job_id={id} — the CVs tailored for one job, newest first. */
export async function listCvs(jobId: number): Promise<Cv[]> {
  const res = await fetch(`${API_BASE}/api/cvs?job_id=${jobId}`)
  if (!res.ok) throw new Error(await readError(res, 'Failed to load CVs'))
  return res.json()
}

/** PATCH /api/cvs/{id} — persist an edit to a tailored CV's markdown content. */
export async function updateCv(id: number, content: string): Promise<Cv> {
  const res = await fetch(`${API_BASE}/api/cvs/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  })
  if (!res.ok) throw new Error(await readError(res, 'Failed to save CV'))
  return res.json()
}

/** Stable React Query key for a job's tailored CVs. */
export const cvsQueryKey = (jobId: number) => ['cvs', jobId] as const
