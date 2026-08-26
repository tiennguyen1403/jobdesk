// Upwork OAuth API client — its own module under lib/api/ (like jobs.ts /
// savedSearches.ts) so sibling clients never collide on merge. Types mirror the
// backend Upwork schema (api/app/schemas/upwork.py, UpworkStatus); the calls
// speak the real /api/upwork contract and never carry a token value.
//
// The whole integration is gated server-side by require_upwork_configured: with
// UPWORK_CLIENT_ID / _SECRET unset every /api/upwork/* route returns a clean 503.
// getUpworkStatus() turns that 503 into a first-class `configured: false` result
// (not a thrown error) so the Sources page renders a plain "not configured" state
// and keeps its error branch for a genuinely unreachable backend.

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

/** Upwork connection status (mirrors UpworkStatus) — never carries a token value. */
export interface UpworkStatus {
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
export interface UpworkStatusResult extends UpworkStatus {
  configured: boolean
}

/** The shape returned when the integration is off (the 503 / credentials-absent case). */
const NOT_CONFIGURED: UpworkStatusResult = {
  provider: 'upwork',
  connected: false,
  expired: false,
  expires_at: null,
  scope: null,
  configured: false,
}

/** Full-page URL that kicks off the OAuth2 flow (the API 307-redirects to Upwork). */
export function upworkConnectUrl(): string {
  return `${API_BASE}/api/upwork/connect`
}

/** Turn a status/disconnect response into a UpworkStatusResult, mapping 503 → not configured. */
async function readStatus(res: Response, fallback: string): Promise<UpworkStatusResult> {
  // 503 = credentials absent (require_upwork_configured) — surface as not configured.
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
  const body = (await res.json()) as UpworkStatus
  return { ...body, configured: true }
}

/** GET /api/upwork/status — whether the Upwork account is connected, and until when. */
export async function getUpworkStatus(): Promise<UpworkStatusResult> {
  const res = await fetch(`${API_BASE}/api/upwork/status`)
  return readStatus(res, 'Failed to load Upwork status')
}

/** POST /api/upwork/disconnect — clear the stored tokens; the account goes offline. */
export async function disconnectUpwork(): Promise<UpworkStatusResult> {
  const res = await fetch(`${API_BASE}/api/upwork/disconnect`, { method: 'POST' })
  return readStatus(res, 'Failed to disconnect Upwork')
}

/** Stable React Query key for the connection status. */
export const upworkStatusQueryKey = () => ['upwork', 'status'] as const
