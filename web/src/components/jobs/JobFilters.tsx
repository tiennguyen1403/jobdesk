import type { BudgetType } from '../../lib/api/jobs'

export interface JobFiltersValue {
  /** Part-time scope guardrail — default ON so full-time postings stay hidden. */
  partTime: boolean
  maxWeeklyHours: string
  budgetType: '' | BudgetType
  /** Provider filter (client-side): '' = any source, else a provider key. */
  source: string
  search: string
}

interface Props {
  value: JobFiltersValue
  onChange: (patch: Partial<JobFiltersValue>) => void
}

const inputClass =
  'rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-100 ' +
  'placeholder:text-slate-500 focus:border-slate-600 focus:outline-none focus:ring-1 focus:ring-slate-600'

export default function JobFilters({ value, onChange }: Props) {
  return (
    <div className="flex flex-wrap items-end gap-4 rounded-xl border border-slate-800 bg-slate-900 p-4">
      <label className="flex cursor-pointer select-none items-center gap-2 text-sm text-slate-200">
        <input
          type="checkbox"
          checked={value.partTime}
          onChange={(e) => onChange({ partTime: e.target.checked })}
          className="h-4 w-4 accent-emerald-500"
        />
        Part-time only
      </label>

      <label className="flex flex-col gap-1 text-xs text-slate-400">
        Max hours / week
        <input
          type="number"
          min={0}
          inputMode="numeric"
          placeholder="any"
          value={value.maxWeeklyHours}
          onChange={(e) => onChange({ maxWeeklyHours: e.target.value })}
          className={`${inputClass} w-28`}
        />
      </label>

      <label className="flex flex-col gap-1 text-xs text-slate-400">
        Budget type
        <select
          value={value.budgetType}
          onChange={(e) => onChange({ budgetType: e.target.value as '' | BudgetType })}
          className={`${inputClass} w-32`}
        >
          <option value="">Any</option>
          <option value="hourly">Hourly</option>
          <option value="fixed">Fixed</option>
        </select>
      </label>

      <label className="flex flex-col gap-1 text-xs text-slate-400">
        Source
        <select
          value={value.source}
          onChange={(e) => onChange({ source: e.target.value })}
          className={`${inputClass} w-32`}
        >
          <option value="">Any</option>
          <option value="manual">Manual</option>
          <option value="capture">Capture</option>
          <option value="upwork">Upwork</option>
          <option value="freelancer">Freelancer</option>
        </select>
      </label>

      <label className="flex flex-1 flex-col gap-1 text-xs text-slate-400">
        Search
        <input
          type="search"
          placeholder="Title or description…"
          value={value.search}
          onChange={(e) => onChange({ search: e.target.value })}
          className={`${inputClass} min-w-48`}
        />
      </label>
    </div>
  )
}
