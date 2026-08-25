const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

export interface HealthResponse {
  status: string
  db: boolean
}

export async function getHealth(): Promise<HealthResponse> {
  const res = await fetch(`${API_BASE}/api/health`)
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}
