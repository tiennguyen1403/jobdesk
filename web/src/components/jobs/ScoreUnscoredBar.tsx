import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { analyticsSummaryQueryKey, getAnalyticsSummary } from '../../lib/api/analytics'
import { scoreUnscored } from '../../lib/api/jobs'

// Score at most this many jobs per click — a hard cap on the paid AI spend one
// press can trigger. The backend enforces the same ceiling.
const BATCH_LIMIT = 25

/**
 * A cost-aware batch scorer for the Jobs page. It reads how many jobs have no
 * match score, confirms before spending (each job is a paid Claude call), runs
 * score_match across the newest unscored ones (up to BATCH_LIMIT), then reports
 * the outcome and refreshes the jobs + analytics feeds. Renders nothing when
 * every job is already scored.
 */
export default function ScoreUnscoredBar() {
  const queryClient = useQueryClient()
  const [confirming, setConfirming] = useState(false)

  const analytics = useQuery({
    queryKey: analyticsSummaryQueryKey(),
    queryFn: () => getAnalyticsSummary(),
  })
  const unscored = analytics.data?.match.unscored ?? 0

  const scoreBatch = useMutation({
    mutationFn: () => scoreUnscored(BATCH_LIMIT),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
      queryClient.invalidateQueries({ queryKey: ['analytics-summary'] })
      setConfirming(false)
    },
  })

  // Nothing to do — every job is scored (and no result to keep showing).
  if (unscored === 0 && !scoreBatch.data) return null

  const willScore = Math.min(unscored, BATCH_LIMIT)
  const result = scoreBatch.data

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-800 bg-slate-900/60 px-4 py-3 text-sm">
      <div className="text-slate-300">
        <span className="font-semibold text-slate-100">{unscored}</span>{' '}
        unscored job{unscored === 1 ? '' : 's'} — AI-score their part-time fit.
        {result && (
          <span className="ml-2 text-emerald-300">
            Scored {result.scored}
            {result.failed > 0 && (
              <span className="text-amber-300"> · {result.failed} failed</span>
            )}
            {' · '}${result.total_cost_usd.toFixed(4)}
            {result.remaining_unscored > 0 && ` · ${result.remaining_unscored} left`}
          </span>
        )}
      </div>

      <div className="flex items-center gap-2">
        {scoreBatch.isError && (
          <span className="text-red-400">
            {scoreBatch.error instanceof Error ? scoreBatch.error.message : 'Scoring failed.'}
          </span>
        )}
        {confirming ? (
          <>
            <span className="text-slate-400">
              Run {willScore} paid AI call{willScore === 1 ? '' : 's'}?
            </span>
            <button
              type="button"
              onClick={() => scoreBatch.mutate()}
              disabled={scoreBatch.isPending}
              className="rounded-lg bg-emerald-500 px-3 py-1.5 font-semibold text-slate-950 transition-colors hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {scoreBatch.isPending ? 'Scoring…' : `Score ${willScore}`}
            </button>
            <button
              type="button"
              onClick={() => setConfirming(false)}
              disabled={scoreBatch.isPending}
              className="rounded-lg px-3 py-1.5 text-slate-400 transition-colors hover:text-slate-200"
            >
              Cancel
            </button>
          </>
        ) : (
          unscored > 0 && (
            <button
              type="button"
              onClick={() => setConfirming(true)}
              className="rounded-lg border border-emerald-600/50 px-3 py-1.5 font-medium text-emerald-300 transition-colors hover:border-emerald-500 hover:bg-emerald-500/10"
            >
              Score unscored →
            </button>
          )
        )}
      </div>
    </div>
  )
}
