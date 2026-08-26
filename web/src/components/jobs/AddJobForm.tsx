import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { createJob, type BudgetType, type JobCreate, type Workload } from '../../lib/api/jobs'

interface FormState {
  url: string
  title: string
  description: string
  budget_type: BudgetType
  budget_min: string
  budget_max: string
  currency: string
  workload: '' | Workload
  weekly_hours: string
  duration: string
  skills: string
}

// Default the workload to part-time: this app only tracks side gigs, so the
// form should nudge toward the in-scope choice.
const EMPTY: FormState = {
  url: '',
  title: '',
  description: '',
  budget_type: 'fixed',
  budget_min: '',
  budget_max: '',
  currency: 'USD',
  workload: 'part_time',
  weekly_hours: '',
  duration: '',
  skills: '',
}

const fieldClass =
  'rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-100 ' +
  'placeholder:text-slate-500 focus:border-slate-600 focus:outline-none focus:ring-1 focus:ring-slate-600'
const labelClass = 'flex flex-col gap-1 text-xs text-slate-400'

/** Turn the string-backed form into a typed JobCreate payload, dropping blanks. */
function toPayload(form: FormState): JobCreate {
  const num = (v: string): number | undefined => {
    const n = Number(v)
    return v.trim() === '' || Number.isNaN(n) ? undefined : n
  }
  return {
    url: form.url.trim(),
    title: form.title.trim(),
    description: form.description.trim() || undefined,
    budget_type: form.budget_type,
    budget_min: num(form.budget_min),
    budget_max: num(form.budget_max),
    currency: form.currency.trim() || 'USD',
    workload: form.workload || undefined,
    weekly_hours: num(form.weekly_hours),
    duration: form.duration.trim() || undefined,
    skills: form.skills
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean),
  }
}

export default function AddJobForm({ onCreated }: { onCreated?: () => void }) {
  const [form, setForm] = useState<FormState>(EMPTY)
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationFn: () => createJob(toPayload(form)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
      setForm(EMPTY)
      onCreated?.()
    },
  })

  const set = <K extends keyof FormState>(key: K, val: FormState[K]) =>
    setForm((f) => ({ ...f, [key]: val }))

  const canSubmit = form.url.trim() !== '' && form.title.trim() !== '' && !mutation.isPending

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        if (canSubmit) mutation.mutate()
      }}
      className="space-y-4 rounded-xl border border-slate-800 bg-slate-900 p-5"
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <label className={`${labelClass} sm:col-span-2`}>
          URL *
          <input
            type="url"
            required
            placeholder="https://www.upwork.com/jobs/~…"
            value={form.url}
            onChange={(e) => set('url', e.target.value)}
            className={fieldClass}
          />
        </label>

        <label className={`${labelClass} sm:col-span-2`}>
          Title *
          <input
            type="text"
            required
            placeholder="e.g. React dashboard tweaks (evenings)"
            value={form.title}
            onChange={(e) => set('title', e.target.value)}
            className={fieldClass}
          />
        </label>

        <label className={`${labelClass} sm:col-span-2`}>
          Description
          <textarea
            rows={3}
            placeholder="What the client needs…"
            value={form.description}
            onChange={(e) => set('description', e.target.value)}
            className={fieldClass}
          />
        </label>

        <label className={labelClass}>
          Budget type
          <select
            value={form.budget_type}
            onChange={(e) => set('budget_type', e.target.value as BudgetType)}
            className={fieldClass}
          >
            <option value="fixed">Fixed</option>
            <option value="hourly">Hourly</option>
          </select>
        </label>

        <label className={labelClass}>
          Currency
          <input
            type="text"
            value={form.currency}
            onChange={(e) => set('currency', e.target.value)}
            className={fieldClass}
          />
        </label>

        <label className={labelClass}>
          Budget min
          <input
            type="number"
            min={0}
            placeholder="0"
            value={form.budget_min}
            onChange={(e) => set('budget_min', e.target.value)}
            className={fieldClass}
          />
        </label>

        <label className={labelClass}>
          Budget max
          <input
            type="number"
            min={0}
            placeholder="0"
            value={form.budget_max}
            onChange={(e) => set('budget_max', e.target.value)}
            className={fieldClass}
          />
        </label>

        <label className={labelClass}>
          Workload
          <select
            value={form.workload}
            onChange={(e) => set('workload', e.target.value as '' | Workload)}
            className={fieldClass}
          >
            <option value="part_time">Part-time</option>
            <option value="full_time">Full-time</option>
            <option value="">Unspecified</option>
          </select>
        </label>

        <label className={labelClass}>
          Weekly hours
          <input
            type="number"
            min={0}
            placeholder="e.g. 10"
            value={form.weekly_hours}
            onChange={(e) => set('weekly_hours', e.target.value)}
            className={fieldClass}
          />
        </label>

        <label className={labelClass}>
          Duration
          <input
            type="text"
            placeholder="e.g. one_to_three_months"
            value={form.duration}
            onChange={(e) => set('duration', e.target.value)}
            className={fieldClass}
          />
        </label>

        <label className={labelClass}>
          Skills (comma-separated)
          <input
            type="text"
            placeholder="React, TypeScript, Tailwind"
            value={form.skills}
            onChange={(e) => set('skills', e.target.value)}
            className={fieldClass}
          />
        </label>
      </div>

      {mutation.isError && (
        <p className="text-sm text-red-400">
          {mutation.error instanceof Error ? mutation.error.message : 'Could not add the job.'}
        </p>
      )}

      <div className="flex items-center gap-3">
        <button
          type="submit"
          disabled={!canSubmit}
          className="rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-slate-950 transition-colors hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {mutation.isPending ? 'Adding…' : 'Add job'}
        </button>
        {onCreated && (
          <button
            type="button"
            onClick={onCreated}
            className="rounded-lg px-4 py-2 text-sm text-slate-400 hover:text-slate-200"
          >
            Cancel
          </button>
        )}
      </div>
    </form>
  )
}
