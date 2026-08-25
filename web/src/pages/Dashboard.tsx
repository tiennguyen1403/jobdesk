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
        <p className="text-slate-500">
          Khung dự án đã chạy. Trạng thái kết nối API &amp; database:
        </p>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        {isLoading && <p className="text-slate-500">Đang kiểm tra API…</p>}
        {isError && (
          <p className="text-red-600">
            Không gọi được API. Kiểm tra backend đã chạy chưa (docker compose up).
          </p>
        )}
        {data && (
          <ul className="space-y-3">
            <li className="flex items-center gap-3">
              <Dot ok={data.status === 'ok'} />
              <span>API:</span>
              <span className="font-mono text-sm">{data.status}</span>
            </li>
            <li className="flex items-center gap-3">
              <Dot ok={data.db} />
              <span>Database:</span>
              <span className="font-mono text-sm">
                {data.db ? 'connected' : 'down'}
              </span>
            </li>
          </ul>
        )}
      </div>

      <p className="text-sm text-slate-400">
        Tiếp theo (Phase 1): model Job + Application, danh sách job và pipeline Kanban —
        lọc riêng job part-time / theo giờ / theo dự án.
      </p>
    </div>
  )
}

function Dot({ ok }: { ok: boolean }) {
  return (
    <span
      className={`inline-block h-2.5 w-2.5 rounded-full ${
        ok ? 'bg-emerald-500' : 'bg-red-500'
      }`}
    />
  )
}
