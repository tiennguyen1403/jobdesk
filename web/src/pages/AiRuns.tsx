import { Fragment, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  KNOWN_AI_FEATURES,
  aiRunsQueryKey,
  listAiRuns,
  type AiRun,
  type AiRunFilters,
  type AiRunStatus,
} from '../lib/api/aiRuns'

/** Cost is tiny per call, so show four decimals (e.g. $0.0123). */
function formatCost(usd: number): string {
  return `$${usd.toFixed(4)}`
}

/** Localised timestamp; fall back to the raw ISO string if it won't parse. */
function formatWhen(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}

/** Roll the loaded rows up into the summary-header figures. */
function summarize(runs: AiRun[] | undefined) {
  const list = runs ?? []
  return {
    count: list.length,
    cost: list.reduce((sum, r) => sum + r.cost_usd, 0),
    tokens: list.reduce((sum, r) => sum + r.input_tokens + r.output_tokens, 0),
  }
}

export default function AiRuns() {
  // Local filter state maps straight onto the backend query params.
  const [feature, setFeature] = useState<string>('')
  const [status, setStatus] = useState<'' | AiRunStatus>('')

  const filters: AiRunFilters = {
    feature: feature || undefined,
    status: status || undefined,
  }

  const { data: runs, isLoading, isError, isFetching } = useQuery({
    queryKey: aiRunsQueryKey(filters),
    queryFn: () => listAiRuns(filters),
  })

  const totals = summarize(runs)

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">AI Runs</h1>
        <p className="text-slate-400">
          Cost &amp; usage ledger — every Claude call (match scoring, CV tailoring, proposal
          drafting) logs one row here. Read-only.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Stat label="Runs" value={String(totals.count)} />
        <Stat label="Total cost" value={formatCost(totals.cost)} />
        <Stat label="Tokens" value={totals.tokens.toLocaleString()} />
      </div>
      <p className="-mt-2 text-xs text-slate-500">Totals cover the runs shown below.</p>

      <div className="flex flex-wrap items-end gap-4">
        <label className="flex flex-col gap-1 text-xs text-slate-400">
          Feature
          <select
            value={feature}
            onChange={(e) => setFeature(e.target.value)}
            className="rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-sm text-slate-200"
          >
            <option value="">All features</option>
            {KNOWN_AI_FEATURES.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-slate-400">
          Status
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value as '' | AiRunStatus)}
            className="rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-sm text-slate-200"
          >
            <option value="">All</option>
            <option value="success">success</option>
            <option value="error">error</option>
          </select>
        </label>
      </div>

      {isLoading ? (
        <p className="text-slate-400">Loading AI runs…</p>
      ) : isError ? (
        <p className="text-red-400">
          Could not load AI runs. Make sure the backend is running (docker compose up).
        </p>
      ) : !runs || runs.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-800 bg-slate-900/40 p-10 text-center">
          <p className="text-slate-300">No AI runs match these filters.</p>
          <p className="mt-1 text-sm text-slate-500">
            Runs appear here once you score a match or generate a CV / proposal in the Studio.
          </p>
        </div>
      ) : (
        <>
          <p className="text-xs text-slate-500">
            {runs.length} run{runs.length === 1 ? '' : 's'}
            {isFetching && ' · refreshing…'}
          </p>
          <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/40">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="text-xs uppercase tracking-wide text-slate-500">
                  <th className="px-4 py-3 font-medium">Feature</th>
                  <th className="px-4 py-3 font-medium">Model</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Tokens (in → out)</th>
                  <th className="px-4 py-3 font-medium">Cost</th>
                  <th className="px-4 py-3 font-medium">When</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <Fragment key={run.id}>
                    <tr className="border-t border-slate-800/70">
                      <td className="px-4 py-3 font-medium text-slate-200">{run.feature}</td>
                      <td className="px-4 py-3 font-mono text-xs text-slate-400">{run.model}</td>
                      <td className="px-4 py-3">
                        <StatusBadge status={run.status} />
                      </td>
                      <td className="px-4 py-3 font-mono text-xs text-slate-300">
                        {run.input_tokens.toLocaleString()} → {run.output_tokens.toLocaleString()}
                      </td>
                      <td className="px-4 py-3 font-mono text-slate-200">
                        {formatCost(run.cost_usd)}
                      </td>
                      <td className="px-4 py-3 text-slate-400">{formatWhen(run.created_at)}</td>
                    </tr>
                    {run.status === 'error' && run.error && (
                      <tr>
                        <td
                          colSpan={6}
                          className="px-4 pb-3 font-mono text-xs text-rose-400/80"
                          title={run.error}
                        >
                          {run.error}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
      <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums text-slate-100">{value}</p>
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  const tone =
    status === 'success'
      ? 'bg-emerald-500/10 text-emerald-400'
      : status === 'error'
        ? 'bg-rose-500/10 text-rose-400'
        : 'bg-slate-700/40 text-slate-300'
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${tone}`}>{status}</span>
  )
}
