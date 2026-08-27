import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  createSavedSearch,
  updateSavedSearch,
  type SavedSearch,
  type SavedSearchCreate,
} from '../../lib/api/savedSearches'
import type { Workload } from '../../lib/api/jobs'

// The job sources a saved search can target. Both are pollable today (Upwork and
// Freelancer OAuth connectors); a new source only has to be added here + in the
// backend poller registry.
const PROVIDERS = ['upwork', 'freelancer'] as const
type Provider = (typeof PROVIDERS)[number]

/** Coerce a stored provider string to a known option (unknown → upwork). */
function toProvider(p: string): Provider {
  return (PROVIDERS as readonly string[]).includes(p) ? (p as Provider) : 'upwork'
}

// String-backed form state (empty strings map to "unset" on submit).
interface FormState {
  name: string
  provider: Provider
  keywords: string
  category: string
  workload: '' | Workload
  max_weekly_hours: string
  enabled: boolean
}

// Default the workload to part-time: JobDesk only tracks side gigs, so the form
// nudges every saved search toward the in-scope, evenings-and-weekends choice.
const EMPTY: FormState = {
  name: '',
  provider: 'upwork',
  keywords: '',
  category: '',
  workload: 'part_time',
  max_weekly_hours: '',
  enabled: true,
}

/** Seed the form from an existing search (edit mode). */
function fromSearch(s: SavedSearch): FormState {
  return {
    name: s.name,
    provider: toProvider(s.provider),
    keywords: s.query.keywords ?? '',
    category: s.query.category ?? '',
    workload: s.query.workload ?? '',
    max_weekly_hours: s.query.max_weekly_hours != null ? String(s.query.max_weekly_hours) : '',
    enabled: s.enabled,
  }
}

/** Turn the string-backed form into the create/update payload, dropping blanks. */
function toPayload(form: FormState): SavedSearchCreate {
  const hours = Number(form.max_weekly_hours)
  return {
    name: form.name.trim(),
    provider: form.provider,
    enabled: form.enabled,
    query: {
      keywords: form.keywords.trim(),
      category: form.category.trim() || null,
      workload: form.workload || null,
      max_weekly_hours:
        form.max_weekly_hours.trim() !== '' && !Number.isNaN(hours) ? hours : null,
    },
  }
}

const fieldClass =
  'rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-100 ' +
  'placeholder:text-slate-500 focus:border-slate-600 focus:outline-none focus:ring-1 focus:ring-slate-600'
const labelClass = 'flex flex-col gap-1 text-xs text-slate-400'

/**
 * Create or edit a saved search. With `initial` supplied it PATCHes that search;
 * otherwise it POSTs a new one. Either way it invalidates the list on success.
 */
export default function SavedSearchForm({
  initial,
  onDone,
}: {
  initial?: SavedSearch
  onDone?: () => void
}) {
  const isEdit = initial != null
  const [form, setForm] = useState<FormState>(initial ? fromSearch(initial) : EMPTY)
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationFn: () =>
      isEdit
        ? updateSavedSearch(initial.id, toPayload(form))
        : createSavedSearch(toPayload(form)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['saved-searches'] })
      if (!isEdit) setForm(EMPTY)
      onDone?.()
    },
  })

  const set = <K extends keyof FormState>(key: K, val: FormState[K]) =>
    setForm((f) => ({ ...f, [key]: val }))

  const canSubmit = form.name.trim() !== '' && !mutation.isPending

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
          Name *
          <input
            type="text"
            required
            placeholder="e.g. Evening React gigs"
            value={form.name}
            onChange={(e) => set('name', e.target.value)}
            className={fieldClass}
          />
        </label>

        <label className={`${labelClass} sm:col-span-2`}>
          Keywords
          <input
            type="text"
            placeholder="react, tailwind, dashboard"
            value={form.keywords}
            onChange={(e) => set('keywords', e.target.value)}
            className={fieldClass}
          />
        </label>

        <label className={labelClass}>
          Source
          <select
            value={form.provider}
            onChange={(e) => set('provider', e.target.value as Provider)}
            className={fieldClass}
          >
            <option value="upwork">Upwork</option>
            <option value="freelancer">Freelancer</option>
          </select>
        </label>

        <label className={labelClass}>
          Category
          <input
            type="text"
            placeholder="e.g. Web Development"
            value={form.category}
            onChange={(e) => set('category', e.target.value)}
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
            <option value="">Any</option>
          </select>
        </label>

        <label className={labelClass}>
          Max weekly hours
          <input
            type="number"
            min={0}
            placeholder="e.g. 20"
            value={form.max_weekly_hours}
            onChange={(e) => set('max_weekly_hours', e.target.value)}
            className={fieldClass}
          />
        </label>

        <label className="flex items-center gap-2 text-sm text-slate-300 sm:col-span-2">
          <input
            type="checkbox"
            checked={form.enabled}
            onChange={(e) => set('enabled', e.target.checked)}
            className="h-4 w-4 rounded border-slate-700 bg-slate-950"
          />
          Enabled — include in scheduled polling
        </label>
      </div>

      <p className="text-xs text-slate-500">
        Part-time scope: constrain the workload / weekly hours so polling only pulls
        evenings-and-weekends work. A saved search only finds jobs — JobDesk never applies
        for you.
      </p>

      {mutation.isError && (
        <p className="text-sm text-red-400">
          {mutation.error instanceof Error ? mutation.error.message : 'Could not save the search.'}
        </p>
      )}

      <div className="flex items-center gap-3">
        <button
          type="submit"
          disabled={!canSubmit}
          className="rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-slate-950 transition-colors hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {mutation.isPending ? 'Saving…' : isEdit ? 'Save changes' : 'Create search'}
        </button>
        {onDone && (
          <button
            type="button"
            onClick={onDone}
            className="rounded-lg px-4 py-2 text-sm text-slate-400 hover:text-slate-200"
          >
            Cancel
          </button>
        )}
      </div>
    </form>
  )
}
