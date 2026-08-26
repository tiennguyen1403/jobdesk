// The Studio's match-score panel: shows the AI part-time fit score (0–100), the
// reasons behind it, and a button to (re)compute it via score_match. Scoring
// weighs availability (workload / weekly hours / duration), so a full-time-
// leaning posting lands low — the scope guardrail, made visible.

interface Props {
  /** 0–100, or null if the job has never been scored. */
  score: number | null
  reasons: string[] | null
  partTimeFit: boolean | null
  /** ISO timestamp of the last scoring, or null. */
  scoredAt: string | null
  onCompute: () => void
  isComputing: boolean
  error?: Error | null
}

/** Emerald ≥70, amber ≥40, else rose — a quick read on evenings-and-weekends fit. */
function scoreTone(score: number): { text: string; ring: string } {
  if (score >= 70) return { text: 'text-emerald-300', ring: 'ring-emerald-500/40' }
  if (score >= 40) return { text: 'text-amber-300', ring: 'ring-amber-500/40' }
  return { text: 'text-rose-300', ring: 'ring-rose-500/40' }
}

function formatDate(iso: string | null): string | null {
  if (!iso) return null
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return null
  return d.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export default function MatchScorePanel({
  score,
  reasons,
  partTimeFit,
  scoredAt,
  onCompute,
  isComputing,
  error,
}: Props) {
  const scored = score != null
  const tone = scored ? scoreTone(score) : null
  const when = formatDate(scoredAt)

  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-sm font-semibold text-slate-200">Match score</h2>
          <p className="mt-0.5 text-xs text-slate-500">
            How well this fits as an evenings-and-weekends side gig.
          </p>
        </div>
        <button
          type="button"
          onClick={onCompute}
          disabled={isComputing}
          className="shrink-0 rounded-lg bg-emerald-500 px-3 py-1.5 text-xs font-semibold text-slate-950 transition-colors hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isComputing ? 'Scoring…' : scored ? 'Recompute' : 'Compute score'}
        </button>
      </div>

      {error && (
        <p className="mt-3 text-sm text-rose-400">{error.message}</p>
      )}

      {scored ? (
        <div className="mt-4 flex gap-5">
          <div
            className={`flex h-20 w-20 shrink-0 flex-col items-center justify-center rounded-full ring-2 ${tone!.ring}`}
          >
            <span className={`text-2xl font-bold ${tone!.text}`}>{score}</span>
            <span className="text-[10px] uppercase tracking-wide text-slate-500">/ 100</span>
          </div>
          <div className="min-w-0 flex-1">
            <span
              className={`inline-block rounded-full px-2.5 py-1 text-xs font-medium ${
                partTimeFit
                  ? 'bg-emerald-500/10 text-emerald-300 ring-1 ring-emerald-500/30'
                  : 'bg-amber-500/10 text-amber-300 ring-1 ring-amber-500/30'
              }`}
            >
              {partTimeFit ? 'Fits part-time' : 'Weak part-time fit'}
            </span>
            {reasons && reasons.length > 0 && (
              <ul className="mt-3 space-y-1.5">
                {reasons.map((reason, i) => (
                  <li key={i} className="flex gap-2 text-sm text-slate-300">
                    <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-slate-500" />
                    <span>{reason}</span>
                  </li>
                ))}
              </ul>
            )}
            {when && <p className="mt-3 text-xs text-slate-600">Scored {when}</p>}
          </div>
        </div>
      ) : (
        !error && (
          <p className="mt-4 text-sm text-slate-500">
            Not scored yet — compute the match to see the fit and its reasons.
          </p>
        )
      )}
    </section>
  )
}
