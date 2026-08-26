import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  disconnectUpwork,
  getUpworkStatus,
  upworkConnectUrl,
  upworkStatusQueryKey,
  type UpworkStatusResult,
} from '../../lib/api/upwork'

/** Localised timestamp; fall back to the raw ISO string if it won't parse. */
function formatWhen(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}

const connectClass =
  'rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-slate-950 ' +
  'transition-colors hover:bg-emerald-400'

export default function UpworkPanel() {
  const queryClient = useQueryClient()

  const { data: status, isLoading, isError } = useQuery({
    queryKey: upworkStatusQueryKey(),
    queryFn: getUpworkStatus,
  })

  // Disconnect returns the fresh (offline) status — write it straight into the
  // cache so the panel flips to "not connected" without a second round-trip.
  const disconnect = useMutation({
    mutationFn: disconnectUpwork,
    onSuccess: (result) => queryClient.setQueryData(upworkStatusQueryKey(), result),
  })

  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900 p-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold">Upwork</h2>
          <p className="mt-1 text-sm text-slate-400">
            OAuth connection for job-search polling. JobDesk reads jobs only — it never
            applies for you.
          </p>
        </div>
        {status?.configured && (
          <ConnectionBadge connected={status.connected} expired={status.expired} />
        )}
      </div>

      <div className="mt-5">
        {isLoading ? (
          <p className="text-slate-400">Checking connection…</p>
        ) : isError ? (
          <p className="text-red-400">
            Could not reach the backend. Make sure it is running (docker compose up).
          </p>
        ) : !status?.configured ? (
          <NotConfigured />
        ) : status.connected ? (
          <Connected
            status={status}
            onDisconnect={() => disconnect.mutate()}
            disconnecting={disconnect.isPending}
          />
        ) : (
          <Disconnected />
        )}

        {disconnect.isError && (
          <p className="mt-3 text-sm text-red-400">
            {disconnect.error instanceof Error ? disconnect.error.message : 'Could not disconnect.'}
          </p>
        )}
      </div>
    </section>
  )
}

function ConnectionBadge({ connected, expired }: { connected: boolean; expired: boolean }) {
  const [label, tone] = !connected
    ? ['Disconnected', 'bg-slate-700/40 text-slate-300']
    : expired
      ? ['Token expired', 'bg-amber-500/10 text-amber-400']
      : ['Connected', 'bg-emerald-500/10 text-emerald-400']
  return <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${tone}`}>{label}</span>
}

function NotConfigured() {
  return (
    <div className="rounded-lg border border-dashed border-slate-700 bg-slate-950/40 p-4">
      <p className="text-sm text-slate-300">Upwork integration is not configured.</p>
      <p className="mt-1 text-xs text-slate-500">
        Set <code className="font-mono text-slate-400">UPWORK_CLIENT_ID</code> and{' '}
        <code className="font-mono text-slate-400">UPWORK_CLIENT_SECRET</code> in{' '}
        <code className="font-mono text-slate-400">.env</code>, then restart the API. Until
        then the integration stays off and polling is a no-op.
      </p>
    </div>
  )
}

function Disconnected() {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <span className="text-sm text-slate-300">Not connected.</span>
      {/* A full-page link, not a fetch: OAuth needs a top-level navigation. */}
      <a href={upworkConnectUrl()} className={connectClass}>
        Connect Upwork
      </a>
    </div>
  )
}

function Connected({
  status,
  onDisconnect,
  disconnecting,
}: {
  status: UpworkStatusResult
  onDisconnect: () => void
  disconnecting: boolean
}) {
  return (
    <div className="space-y-4">
      <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-3">
        <Field label="Status" value={status.expired ? 'Token expired' : 'Connected'} />
        <Field label="Expires" value={formatWhen(status.expires_at)} />
        <Field label="Scope" value={status.scope || '—'} />
      </dl>
      <div className="flex flex-wrap items-center gap-3">
        {status.expired && (
          <a href={upworkConnectUrl()} className={connectClass}>
            Reconnect
          </a>
        )}
        <button
          type="button"
          onClick={onDisconnect}
          disabled={disconnecting}
          className="rounded-lg border border-slate-700 px-4 py-2 text-sm font-medium text-slate-300 transition-colors hover:border-slate-600 hover:text-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {disconnecting ? 'Disconnecting…' : 'Disconnect'}
        </button>
      </div>
    </div>
  )
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className="mt-0.5 break-words text-slate-200">{value}</dd>
    </div>
  )
}
