import type { ReactElement } from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import Studio from './Studio'
import { scoreMatch } from '../lib/api/jobs'

// Stub the resource clients so the test never hits the network. Fixtures live
// inside each factory: vi.mock is hoisted, so it must not close over any
// top-level binding.
vi.mock('../lib/api/jobs', () => {
  const sampleJob = {
    id: 1,
    source: 'manual',
    external_id: null,
    url: 'https://www.upwork.com/jobs/~sample',
    title: 'React dashboard tweaks (evenings)',
    description: 'Small React + Tailwind fixes.',
    budget_type: 'hourly',
    budget_min: 30,
    budget_max: 50,
    currency: 'USD',
    workload: 'part_time',
    weekly_hours: 10,
    duration: 'one_to_three_months',
    skills: ['React'],
    client_country: 'Germany',
    posted_at: '2026-08-25T09:00:00Z',
    match_score: 82,
    match_reasons: ['Light weekly hours suit evenings', 'React skills match well'],
    match_part_time_fit: true,
    match_scored_at: '2026-08-26T04:27:03Z',
    created_at: '2026-08-26T04:27:03Z',
    updated_at: '2026-08-26T04:27:03Z',
    application: { id: 1, status: 'saved' },
  }
  return {
    getJob: vi.fn().mockResolvedValue(sampleJob),
    jobQueryKey: (id: number) => ['job', id],
    scoreMatch: vi.fn().mockResolvedValue({ job_id: 1, score: 82 }),
    tailorCv: vi.fn(),
    draftProposal: vi.fn(),
  }
})

vi.mock('../lib/api/cvs', () => ({
  listCvs: vi.fn().mockResolvedValue([]),
  updateCv: vi.fn(),
  cvsQueryKey: (jobId: number) => ['cvs', jobId],
}))

vi.mock('../lib/api/proposals', () => ({
  listProposals: vi.fn().mockResolvedValue([]),
  updateProposal: vi.fn(),
  proposalsQueryKey: (jobId: number) => ['proposals', jobId],
}))

function renderStudio(ui: ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/studio/1']}>
        <Routes>
          <Route path="/studio/:jobId" element={ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('Studio page', () => {
  it('renders the job title once the job loads', async () => {
    renderStudio(<Studio />)
    expect(
      await screen.findByRole('heading', { name: /React dashboard tweaks/i }),
    ).toBeDefined()
  })

  it('shows the match score and its reasons', async () => {
    renderStudio(<Studio />)
    expect(await screen.findByText('82')).toBeDefined()
    expect(screen.getByText(/fits part-time/i)).toBeDefined()
    expect(screen.getByText(/React skills match well/i)).toBeDefined()
  })

  it('offers CV and proposal generation when none exist yet', async () => {
    renderStudio(<Studio />)
    expect(await screen.findByRole('button', { name: /generate cv/i })).toBeDefined()
    expect(screen.getByRole('button', { name: /generate proposal/i })).toBeDefined()
  })

  it('recomputing the score calls score_match for the job', async () => {
    renderStudio(<Studio />)
    fireEvent.click(await screen.findByRole('button', { name: /recompute/i }))
    await waitFor(() => expect(vi.mocked(scoreMatch)).toHaveBeenCalledWith(1))
  })
})
