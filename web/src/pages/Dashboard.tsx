import { useQuery } from '@tanstack/react-query'
import { getHealth } from '../lib/api'

export default function Dashboard() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['health'],
    queryFn: getHealth,
  })

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-slate-400">Project skeleton is running. API &amp; database status:</p>
      </div>

      <div className="rounded-xl border border-slate-800 bg-slate-900 p-6">
        {isLoading && <p className="text-slate-400">Checking API…</p>}
        {isError && (
          <p className="text-red-400">
            Could not reach the API. Make sure the backend is running (docker compose up).
          </p>
        )}
        {data && (
          <ul className="space-y-3">
            <li className="flex items-center gap-3">
              <Dot ok={data.status === 'ok'} />
              <span>API:</span>
              <span className="font-mono text-sm text-slate-300">{data.status}</span>
            </li>
            <li className="flex items-center gap-3">
              <Dot ok={data.db} />
              <span>Database:</span>
              <span className="font-mono text-sm text-slate-300">
                {data.db ? 'connected' : 'down'}
              </span>
            </li>
          </ul>
        )}
      </div>

      <p className="text-sm text-slate-500">
        Next (Phase 1): Job + Application models, job list and pipeline Kanban — filtered to
        part-time / hourly / project work.
      </p>
    </div>
  )
}

function Dot({ ok }: { ok: boolean }) {
  return (
    <span
      className={`inline-block h-2.5 w-2.5 rounded-full ${ok ? 'bg-emerald-400' : 'bg-red-400'}`}
    />
  )
}
