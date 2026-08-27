import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { listSavedSearches, savedSearchesQueryKey } from '../lib/api/savedSearches'
import { upworkStatusQueryKey } from '../lib/api/upwork'
import { freelancerStatusQueryKey } from '../lib/api/freelancer'
import UpworkPanel from '../components/sources/UpworkPanel'
import FreelancerPanel from '../components/sources/FreelancerPanel'
import SavedSearchForm from '../components/sources/SavedSearchForm'
import SavedSearchCard from '../components/sources/SavedSearchCard'

type ConnectBanner = { tone: 'success' | 'error'; text: string }

// The OAuth connectors that redirect back to this page. Each (Upwork #70,
// Freelancer #75) lands with ?<param>=connected or ?<param>=error&reason=<short>;
// the effect below turns the first match into a banner, refreshes that provider's
// cached status on success, and strips the params. Adding a provider = one row
// here plus its panel.
const OAUTH_PROVIDERS = [
  { param: 'upwork', label: 'Upwork', statusKey: upworkStatusQueryKey },
  { param: 'freelancer', label: 'Freelancer', statusKey: freelancerStatusQueryKey },
] as const

/**
 * Friendly copy for each failure `reason` an OAuth callback can carry — denied ·
 * state · upstream · missing_code, the same set for every connector. Unknown → a
 * safe default so a new backend reason never renders a blank banner.
 */
function oauthErrorMessage(provider: string, reason: string | null): string {
  switch (reason) {
    case 'denied':
      return `You declined the ${provider} authorization — nothing was connected.`
    case 'state':
      return `The ${provider} sign-in could not be verified (state mismatch). Please try connecting again.`
    case 'upstream':
      return `${provider} rejected the connection. Please try again in a moment.`
    case 'missing_code':
      return `${provider} did not return an authorization code. Please try connecting again.`
    default:
      return `Could not connect to ${provider}. Please try again.`
  }
}

export default function Sources() {
  const [showForm, setShowForm] = useState(false)
  const [banner, setBanner] = useState<ConnectBanner | null>(null)
  const [searchParams, setSearchParams] = useSearchParams()
  const queryClient = useQueryClient()

  // Each connector redirects back here with ?<provider>=connected or
  // ?<provider>=error&reason=<short>. Turn the first match into an explicit
  // banner, refresh that provider's cached status on success, then strip the
  // params so a refresh or back-button doesn't re-show the banner and the
  // address bar stays clean.
  useEffect(() => {
    for (const p of OAUTH_PROVIDERS) {
      const outcome = searchParams.get(p.param)
      if (!outcome) continue
      if (outcome === 'connected') {
        setBanner({ tone: 'success', text: `${p.label} connected.` })
        queryClient.invalidateQueries({ queryKey: p.statusKey() })
      } else if (outcome === 'error') {
        setBanner({ tone: 'error', text: oauthErrorMessage(p.label, searchParams.get('reason')) })
      }
      setSearchParams({}, { replace: true })
      break
    }
  }, [searchParams, queryClient, setSearchParams])

  const { data: searches, isLoading, isError, isFetching } = useQuery({
    queryKey: savedSearchesQueryKey(),
    queryFn: () => listSavedSearches(),
  })

  return (
    <div className="space-y-10">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Sources</h1>
        <p className="text-slate-400">
          Connect Upwork and Freelancer, and manage the saved searches the poller runs.
          JobDesk only finds and tracks work — it never applies for you.
        </p>
      </div>

      {banner && <ConnectResultBanner banner={banner} onDismiss={() => setBanner(null)} />}

      <div className="grid gap-6 lg:grid-cols-2">
        <UpworkPanel />
        <FreelancerPanel />
      </div>

      <section className="space-y-4">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold">Saved searches</h2>
            <p className="text-sm text-slate-400">
              Part-time-scoped queries the scheduler polls. Run one now to ingest immediately.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setShowForm((v) => !v)}
            className="shrink-0 rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-slate-950 transition-colors hover:bg-emerald-400"
          >
            {showForm ? 'Close' : '+ New search'}
          </button>
        </div>

        {showForm && <SavedSearchForm onDone={() => setShowForm(false)} />}

        {isLoading ? (
          <p className="text-slate-400">Loading saved searches…</p>
        ) : isError ? (
          <p className="text-red-400">
            Could not load saved searches. Make sure the backend is running (docker compose up).
          </p>
        ) : !searches || searches.length === 0 ? (
          <div className="rounded-xl border border-dashed border-slate-800 bg-slate-900/40 p-10 text-center">
            <p className="text-slate-300">No saved searches yet.</p>
            <p className="mt-1 text-sm text-slate-500">
              Create one to have the poller pull part-time gigs on a schedule.
            </p>
          </div>
        ) : (
          <>
            <p className="text-xs text-slate-500">
              {searches.length} search{searches.length === 1 ? '' : 'es'}
              {isFetching && ' · refreshing…'}
            </p>
            <ul className="space-y-4">
              {searches.map((s) => (
                <li key={s.id}>
                  <SavedSearchCard search={s} />
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
    </div>
  )
}

/** Dismissible success/error banner shown after the Upwork OAuth redirect. */
function ConnectResultBanner({
  banner,
  onDismiss,
}: {
  banner: ConnectBanner
  onDismiss: () => void
}) {
  const tone =
    banner.tone === 'success'
      ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400'
      : 'border-red-500/30 bg-red-500/10 text-red-400'
  return (
    <div
      role={banner.tone === 'success' ? 'status' : 'alert'}
      className={`flex items-start justify-between gap-4 rounded-lg border px-4 py-3 text-sm ${tone}`}
    >
      <span>{banner.text}</span>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss"
        className="shrink-0 text-slate-500 transition-colors hover:text-slate-300"
      >
        ✕
      </button>
    </div>
  )
}
