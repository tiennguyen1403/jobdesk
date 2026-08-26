import { Link, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  draftProposal,
  getJob,
  jobQueryKey,
  scoreMatch,
  tailorCv,
  type Job,
} from '../lib/api/jobs'
import { cvsQueryKey, listCvs, updateCv } from '../lib/api/cvs'
import { listProposals, proposalsQueryKey, updateProposal } from '../lib/api/proposals'
import MatchScorePanel from '../components/studio/MatchScorePanel'
import StudioDocPanel from '../components/studio/StudioDocPanel'

/** Currency-aware budget label, e.g. "$30–$50/hr" or "$500 fixed". */
function formatBudget(job: Job): string {
  const money = (n: number) =>
    new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency: job.currency || 'USD',
      maximumFractionDigits: 0,
    }).format(n)

  const { budget_min: min, budget_max: max, budget_type: type } = job
  const suffix = type === 'hourly' ? '/hr' : ' fixed'

  let amount: string
  if (min != null && max != null) amount = min === max ? money(min) : `${money(min)}–${money(max)}`
  else if (min != null) amount = `${money(min)}+`
  else if (max != null) amount = `up to ${money(max)}`
  else return type === 'hourly' ? 'Rate n/a' : 'Budget n/a'

  return `${amount}${suffix}`
}

/** 'one_to_three_months' -> 'one to three months'. */
function humanize(value: string): string {
  return value.replace(/_/g, ' ')
}

export default function Studio() {
  const { jobId: jobIdParam } = useParams()
  const jobId = Number(jobIdParam)
  const validId = Number.isInteger(jobId) && jobId > 0
  const queryClient = useQueryClient()

  const jobQuery = useQuery({
    queryKey: jobQueryKey(jobId),
    queryFn: () => getJob(jobId),
    enabled: validId,
  })
  const cvsQuery = useQuery({
    queryKey: cvsQueryKey(jobId),
    queryFn: () => listCvs(jobId),
    enabled: validId,
  })
  const proposalsQuery = useQuery({
    queryKey: proposalsQueryKey(jobId),
    queryFn: () => listProposals(jobId),
    enabled: validId,
  })

  // The panels always edit the newest tailored CV / proposal for this job.
  const latestCv = cvsQuery.data?.[0] ?? null
  const latestProposal = proposalsQuery.data?.[0] ?? null

  const scoreMutation = useMutation({
    mutationFn: () => scoreMatch(jobId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: jobQueryKey(jobId) }),
  })
  const tailorMutation = useMutation({
    mutationFn: () => tailorCv(jobId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: cvsQueryKey(jobId) }),
  })
  const draftMutation = useMutation({
    mutationFn: () => draftProposal(jobId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: proposalsQueryKey(jobId) }),
  })
  const saveCvMutation = useMutation({
    mutationFn: ({ id, content }: { id: number; content: string }) => updateCv(id, content),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: cvsQueryKey(jobId) }),
  })
  const saveProposalMutation = useMutation({
    mutationFn: ({ id, content }: { id: number; content: string }) => updateProposal(id, content),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: proposalsQueryKey(jobId) }),
  })

  const asError = (e: unknown): Error | null => (e instanceof Error ? e : null)

  if (!validId) {
    return (
      <div className="space-y-4">
        <BackLink />
        <p className="text-rose-400">Invalid job id.</p>
      </div>
    )
  }

  if (jobQuery.isLoading) {
    return (
      <div className="space-y-4">
        <BackLink />
        <p className="text-slate-400">Loading studio…</p>
      </div>
    )
  }

  if (jobQuery.isError || !jobQuery.data) {
    return (
      <div className="space-y-4">
        <BackLink />
        <p className="text-rose-400">
          {asError(jobQuery.error)?.message ??
            'Could not load this job. Make sure the backend is running (docker compose up).'}
        </p>
      </div>
    )
  }

  const job = jobQuery.data
  const partTime = job.workload === 'part_time'

  return (
    <div className="space-y-6">
      <div className="space-y-3">
        <BackLink />
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">{job.title}</h1>
            <a
              href={job.url}
              target="_blank"
              rel="noreferrer"
              className="text-sm text-slate-400 hover:text-emerald-300 hover:underline"
            >
              View the original posting ↗
            </a>
          </div>
          <span className="shrink-0 whitespace-nowrap rounded-lg bg-slate-800 px-3 py-1.5 font-mono text-sm text-emerald-300">
            {formatBudget(job)}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          {job.workload && (
            <span
              className={`rounded-full px-2.5 py-1 font-medium ${
                partTime
                  ? 'bg-emerald-500/10 text-emerald-300 ring-1 ring-emerald-500/30'
                  : 'bg-amber-500/10 text-amber-300 ring-1 ring-amber-500/30'
              }`}
            >
              {humanize(job.workload)}
            </span>
          )}
          {job.weekly_hours != null && (
            <span className="rounded-full bg-slate-800 px-2.5 py-1 text-slate-300">
              ~{job.weekly_hours}h/wk
            </span>
          )}
          {job.duration && (
            <span className="rounded-full bg-slate-800 px-2.5 py-1 text-slate-300">
              {humanize(job.duration)}
            </span>
          )}
        </div>
        <p className="text-sm text-slate-500">
          Generate a tailored CV and a proposal draft, edit them, then copy the proposal to apply
          manually on the platform — JobDesk never submits for you.
        </p>
      </div>

      <MatchScorePanel
        score={job.match_score}
        reasons={job.match_reasons}
        partTimeFit={job.match_part_time_fit}
        scoredAt={job.match_scored_at}
        onCompute={() => scoreMutation.mutate()}
        isComputing={scoreMutation.isPending}
        error={asError(scoreMutation.error)}
      />

      <div className="grid gap-6 lg:grid-cols-2">
        <StudioDocPanel
          key={latestCv ? `cv-${latestCv.id}` : 'cv-none'}
          title="Tailored CV"
          description="The base CV rewritten to match this job."
          initialContent={latestCv?.content ?? ''}
          hasDoc={latestCv != null}
          generateLabel="Generate CV"
          regenerateLabel="Regenerate"
          emptyHint="No tailored CV yet. Generate one from your base CV, then edit the markdown."
          onGenerate={() => tailorMutation.mutate()}
          isGenerating={tailorMutation.isPending}
          generateError={asError(tailorMutation.error)}
          onSave={(content) => latestCv && saveCvMutation.mutate({ id: latestCv.id, content })}
          isSaving={saveCvMutation.isPending}
          saveError={asError(saveCvMutation.error)}
          genMeta={tailorMutation.data ?? null}
        />

        <StudioDocPanel
          key={latestProposal ? `proposal-${latestProposal.id}` : 'proposal-none'}
          title="Proposal draft"
          description="A cover-letter draft grounded in your CV — copy it to apply."
          initialContent={latestProposal?.content ?? ''}
          hasDoc={latestProposal != null}
          generateLabel="Generate proposal"
          regenerateLabel="Regenerate"
          emptyHint="No proposal yet. Generate a draft, edit it, then copy it to apply on the platform."
          onGenerate={() => draftMutation.mutate()}
          isGenerating={draftMutation.isPending}
          generateError={asError(draftMutation.error)}
          onSave={(content) =>
            latestProposal && saveProposalMutation.mutate({ id: latestProposal.id, content })
          }
          isSaving={saveProposalMutation.isPending}
          saveError={asError(saveProposalMutation.error)}
          genMeta={draftMutation.data ?? null}
          showCopy
        />
      </div>
    </div>
  )
}

function BackLink() {
  return (
    <Link to="/jobs" className="text-sm text-slate-400 transition-colors hover:text-slate-200">
      ← Back to jobs
    </Link>
  )
}
