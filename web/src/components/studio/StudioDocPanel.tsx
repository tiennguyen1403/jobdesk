import { useState } from 'react'

// A reusable Studio document panel — the markdown editor shared by the tailored
// CV and the proposal draft. It owns the local edit buffer only; generating,
// saving and loading are the parent's mutations/queries. The parent gives the
// panel a React `key` tied to the document's id, so a freshly generated doc
// remounts the panel with the new content as its starting point.

interface GenMeta {
  model: string
  cost_usd: number
}

interface Props {
  title: string
  description: string
  /** The document's current content ('' when none exists yet). */
  initialContent: string
  /** Whether a document exists — switches between empty-state and editor. */
  hasDoc: boolean
  /** Verb for the primary action, e.g. "Generate CV". */
  generateLabel: string
  /** Verb once a doc exists, e.g. "Regenerate". */
  regenerateLabel: string
  /** Shown in the empty state to explain what generating will do. */
  emptyHint: string
  onGenerate: () => void
  isGenerating: boolean
  generateError?: Error | null
  onSave: (content: string) => void
  isSaving: boolean
  saveError?: Error | null
  /** The last AI generation's accounting, shown as a footnote. */
  genMeta?: GenMeta | null
  /** Show a Copy button (for the proposal — the user pastes it to apply manually). */
  showCopy?: boolean
}

export default function StudioDocPanel({
  title,
  description,
  initialContent,
  hasDoc,
  generateLabel,
  regenerateLabel,
  emptyHint,
  onGenerate,
  isGenerating,
  generateError,
  onSave,
  isSaving,
  saveError,
  genMeta,
  showCopy = false,
}: Props) {
  const [draft, setDraft] = useState(initialContent)
  const [copied, setCopied] = useState(false)
  const dirty = draft !== initialContent

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(draft)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      // Clipboard unavailable (e.g. insecure context) — nothing to do.
    }
  }

  return (
    <section className="flex flex-col rounded-xl border border-slate-800 bg-slate-900 p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-sm font-semibold text-slate-200">{title}</h2>
          <p className="mt-0.5 text-xs text-slate-500">{description}</p>
        </div>
        <button
          type="button"
          onClick={onGenerate}
          disabled={isGenerating}
          className="shrink-0 rounded-lg bg-emerald-500 px-3 py-1.5 text-xs font-semibold text-slate-950 transition-colors hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isGenerating ? 'Generating…' : hasDoc ? regenerateLabel : generateLabel}
        </button>
      </div>

      {generateError && <p className="mt-3 text-sm text-rose-400">{generateError.message}</p>}

      {hasDoc ? (
        <>
          <textarea
            aria-label={`${title} content`}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            spellCheck={false}
            className="mt-4 h-96 w-full resize-y rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 font-mono text-xs leading-relaxed text-slate-100 focus:border-slate-600 focus:outline-none focus:ring-1 focus:ring-slate-600"
          />

          <div className="mt-3 flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={() => onSave(draft)}
              disabled={!dirty || isSaving}
              className="rounded-lg bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-900 transition-colors hover:bg-white disabled:cursor-not-allowed disabled:opacity-40"
            >
              {isSaving ? 'Saving…' : 'Save edits'}
            </button>
            {showCopy && (
              <button
                type="button"
                onClick={copy}
                className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-medium text-slate-200 transition-colors hover:border-slate-500 hover:text-white"
              >
                {copied ? 'Copied!' : 'Copy'}
              </button>
            )}
            <span className="text-xs text-slate-600">
              {dirty ? 'Unsaved changes' : 'Saved'}
            </span>
            {genMeta && (
              <span className="ml-auto font-mono text-[10px] text-slate-600">
                {genMeta.model} · ${genMeta.cost_usd.toFixed(4)}
              </span>
            )}
          </div>

          {saveError && <p className="mt-2 text-sm text-rose-400">{saveError.message}</p>}
        </>
      ) : (
        !generateError && <p className="mt-4 text-sm text-slate-500">{emptyHint}</p>
      )}
    </section>
  )
}
