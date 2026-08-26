import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  APPLICATION_STAGES,
  STAGE_LABELS,
  applicationsQueryKey,
  listApplications,
  updateApplication,
  type ApplicationCard,
  type ApplicationStatus,
  type ApplicationUpdate,
} from '../lib/api/applications'
import PipelineCard from '../components/pipeline/PipelineCard'

interface MoveVars {
  id: number
  patch: ApplicationUpdate
}

export default function Pipeline() {
  const queryClient = useQueryClient()
  // Native HTML5 drag-and-drop state: which card is in hand, which column it's over.
  const [dragId, setDragId] = useState<number | null>(null)
  const [overStage, setOverStage] = useState<ApplicationStatus | null>(null)

  const {
    data: cards,
    isLoading,
    isError,
    isFetching,
  } = useQuery({
    queryKey: applicationsQueryKey(),
    queryFn: () => listApplications(),
  })

  const mutation = useMutation({
    mutationFn: ({ id, patch }: MoveVars) => updateApplication(id, patch),
    // Optimistic: reflect a move / notes edit in the board immediately, then roll
    // back if the PATCH fails. onSettled re-syncs with the server either way.
    onMutate: async ({ id, patch }: MoveVars) => {
      await queryClient.cancelQueries({ queryKey: applicationsQueryKey() })
      const prev = queryClient.getQueryData<ApplicationCard[]>(applicationsQueryKey())
      if (prev) {
        queryClient.setQueryData<ApplicationCard[]>(
          applicationsQueryKey(),
          prev.map((c) => (c.id === id ? { ...c, ...patch } : c)),
        )
      }
      return { prev }
    },
    onError: (_err, _vars, context) => {
      if (context?.prev) queryClient.setQueryData(applicationsQueryKey(), context.prev)
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['applications'] }),
  })

  const move = (id: number, status: ApplicationStatus) => {
    const card = cards?.find((c) => c.id === id)
    if (!card || card.status === status) return
    mutation.mutate({ id, patch: { status } })
  }

  const saveNotes = (id: number, notes: string) => {
    const card = cards?.find((c) => c.id === id)
    const next = notes.trim() === '' ? null : notes
    if (!card || (card.notes ?? null) === next) return
    mutation.mutate({ id, patch: { notes: next } })
  }

  const pendingId = mutation.isPending ? mutation.variables?.id ?? null : null

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Pipeline</h1>
        <p className="text-slate-400">
          Track each application through the funnel — drag a card between columns, or use its
          “Move to” menu. Tracking-only: JobDesk never auto-applies.
        </p>
      </div>

      {isLoading ? (
        <p className="text-slate-400">Loading pipeline…</p>
      ) : isError ? (
        <p className="text-red-400">
          Could not load the pipeline. Make sure the backend is running (docker compose up).
        </p>
      ) : (cards?.length ?? 0) === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-800 bg-slate-900/40 p-10 text-center">
          <p className="text-slate-300">No applications yet.</p>
          <p className="mt-1 text-sm text-slate-500">
            Add a job on the Jobs page — every job starts a card here at “Saved”.
          </p>
        </div>
      ) : (
        <>
          {isFetching && <p className="text-xs text-slate-500">refreshing…</p>}
          <div className="flex gap-4 overflow-x-auto pb-4">
            {APPLICATION_STAGES.map((stage) => {
              const column = (cards ?? []).filter((c) => c.status === stage)
              const isOver = overStage === stage
              return (
                <section
                  key={stage}
                  onDragOver={(e) => {
                    e.preventDefault()
                    setOverStage(stage)
                  }}
                  onDragLeave={() => setOverStage((s) => (s === stage ? null : s))}
                  onDrop={(e) => {
                    e.preventDefault()
                    if (dragId != null) move(dragId, stage)
                    setDragId(null)
                    setOverStage(null)
                  }}
                  className={`flex w-72 shrink-0 flex-col rounded-xl border transition-colors ${
                    isOver ? 'border-emerald-500/60 bg-slate-900' : 'border-slate-800 bg-slate-900/40'
                  }`}
                >
                  <header className="flex items-center justify-between border-b border-slate-800 px-3 py-2">
                    <h2 className="text-sm font-semibold text-slate-200">{STAGE_LABELS[stage]}</h2>
                    <span className="rounded-full bg-slate-800 px-2 py-0.5 font-mono text-xs text-slate-400">
                      {column.length}
                    </span>
                  </header>
                  <div className="flex flex-1 flex-col gap-3 p-3">
                    {column.length === 0 ? (
                      <p className="rounded-lg border border-dashed border-slate-800 px-3 py-6 text-center text-xs text-slate-600">
                        Drop a card here
                      </p>
                    ) : (
                      column.map((card) => (
                        <PipelineCard
                          key={card.id}
                          card={card}
                          isUpdating={pendingId === card.id}
                          onMove={(status) => move(card.id, status)}
                          onSaveNotes={(notes) => saveNotes(card.id, notes)}
                          onDragStart={() => setDragId(card.id)}
                          onDragEnd={() => {
                            setDragId(null)
                            setOverStage(null)
                          }}
                        />
                      ))
                    )}
                  </div>
                </section>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}
