import { Routes, Route, NavLink } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import Jobs from './pages/Jobs'

const navClass = ({ isActive }: { isActive: boolean }) =>
  `text-sm transition-colors ${
    isActive ? 'font-medium text-slate-100' : 'text-slate-400 hover:text-slate-200'
  }`

export default function App() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800 bg-slate-900">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-8">
            <NavLink to="/" className="text-lg font-semibold tracking-tight text-slate-100">
              JobDesk
            </NavLink>
            <nav className="flex items-center gap-6">
              <NavLink to="/" end className={navClass}>
                Dashboard
              </NavLink>
              <NavLink to="/jobs" className={navClass}>
                Jobs
              </NavLink>
              <NavLink to="/pipeline" className={navClass}>
                Pipeline
              </NavLink>
            </nav>
          </div>
          <span className="rounded-full bg-slate-800 px-3 py-1 font-mono text-xs text-slate-400">
            Phase 1 · tracker
          </span>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-6 py-10">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/jobs" element={<Jobs />} />
          <Route path="/pipeline" element={<PipelinePlaceholder />} />
        </Routes>
      </main>
    </div>
  )
}

// Temporary stop-gap so the Pipeline nav link isn't dead; the Kanban board
// arrives in its own Phase 1 issue, which replaces this element.
function PipelinePlaceholder() {
  return (
    <div className="space-y-2">
      <h1 className="text-2xl font-bold tracking-tight">Pipeline</h1>
      <p className="text-slate-400">The Kanban board lands in a later Phase 1 issue.</p>
    </div>
  )
}
