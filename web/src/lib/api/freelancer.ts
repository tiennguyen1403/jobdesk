// Freelancer OAuth API client — a deliberate sibling of upwork.ts (its own
// module under lib/api/ like jobs.ts / savedSearches.ts) so the two clients
// never collide on merge. Types mirror the backend Freelancer schema
// (api/app/schemas/freelancer.py, FreelancerStatus); the calls speak the real
// /api/freelancer contract and never carry a token value.
//
// The whole integration is gated server-side by require_freelancer_configured:
// with FREELANCER_CLIENT_ID / _SECRET unset every /api/freelancer/* route returns
// a clean 503. getFreelancerStatus() turns that 503 into a first-class
// `configured: false` result (not a thrown error) so the Sources page renders a
// plain "not configured" state and keeps its error branch for a genuinely
// unreachable backend.

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

/** Freelancer connection status (mirrors FreelancerStatus) — never carries a token value. */
export interface FreelancerStatus {
  provider: string
  connected: boolean
  expired: boolean
  expires_at: string | null
  scope: string | null
}

/**
 * Status plus whether the integration is configured at all. `configured: false`
 * is the 503 case (credentials absent) — a normal state to render, not an error.
 */
export interface FreelancerStatusResult extends FreelancerStatus {
  configured: boolean
}

/** The shape returned when the integration is off (the 503 / credentials-absent case). */
const NOT_CONFIGURED: FreelancerStatusResult = {
  provider: 'freelancer',
  connected: false,
  expired: false,
  expires_at: null,
  scope: null,
  configured: false,
}

/** Full-page URL that kicks off the OAuth2 flow (the API 307-redirects to Freelancer). */
export function freelancerConnectUrl(): string {
  return `${API_BASE}/api/freelancer/connect`
}

/** Turn a status/disconnect response into a FreelancerStatusResult, mapping 503 → not configured. */
async function readStatus(res: Response, fallback: string): Promise<FreelancerStatusResult> {
  // 503 = credentials absent (require_freelancer_configured) — surface as not configured.
  if (res.status === 503) return NOT_CONFIGURED
  if (!res.ok) {
    let detail = ''
    try {
      const body = await res.json()
      if (body && typeof body.detail === 'string') detail = body.detail
    } catch {
      // Non-JSON body — fall through to the status-coded fallback.
    }
    throw new Error(detail || `${fallback} (${res.status})`)
  }
  const body = (await res.json()) as FreelancerStatus
  return { ...body, configured: true }
}

/** GET /api/freelancer/status — whether the Freelancer account is connected, and until when. */
export async function getFreelancerStatus(): Promise<FreelancerStatusResult> {
  const res = await fetch(`${API_BASE}/api/freelancer/status`)
  return readStatus(res, 'Failed to load Freelancer status')
}

/** POST /api/freelancer/disconnect — clear the stored tokens; the account goes offline. */
export async function disconnectFreelancer(): Promise<FreelancerStatusResult> {
  const res = await fetch(`${API_BASE}/api/freelancer/disconnect`, { method: 'POST' })
  return readStatus(res, 'Failed to disconnect Freelancer')
}

/** Stable React Query key for the connection status. */
export const freelancerStatusQueryKey = () => ['freelancer', 'status'] as const
