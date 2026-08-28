import type { ReactElement } from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import Jobs from './Jobs'
import { listJobs, type Job } from '../lib/api/jobs'

// Stub the jobs client so the test never hits the network. The fixture lives
// inside the factory: vi.mock is hoisted above the file, so it must not close
// over any top-level binding.
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
    skills: ['React', 'TypeScript'],
    client_country: 'Germany',
    posted_at: '2026-08-25T09:00:00Z',
    created_at: '2026-08-26T04:27:03Z',
    updated_at: '2026-08-26T04:27:03Z',
    application: null,
  }
  return {
    listJobs: vi.fn().mockResolvedValue([sampleJob]),
    createJob: vi.fn(),
    createApplicationForJob: vi.fn().mockResolvedValue({}),
    scoreUnscored: vi.fn(),
    jobsQueryKey: (filters = {}) => ['jobs', filters],
  }
})

// The Jobs page renders <ScoreUnscoredBar/>, which reads analytics. Stub it with
// zero unscored so the bar stays hidden and doesn't interfere with these tests.
vi.mock('../lib/api/analytics', () => ({
  getAnalyticsSummary: vi.fn().mockResolvedValue({
    jobs: { total: 0, by_source: {} },
    match: { scored: 0, unscored: 0, part_time_fit: 0, bands: { low: 0, medium: 0, high: 0 } },
    pipeline: { total: 0, by_status: {}, applied_conversion: 0 },
    ai: { total_cost_usd: 0, input_tokens: 0, output_tokens: 0, by_feature: [], days: 30, recent: [] },
  }),
  analyticsSummaryQueryKey: (days?: number) => ['analytics-summary', days],
}))

/** A complete Job for tests that need more than the factory's single fixture. */
function makeJob(overrides: Partial<Job> = {}): Job {
  return {
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
    skills: [],
    client_country: 'Germany',
    posted_at: '2026-08-25T09:00:00Z',
    match_score: null,
    match_reasons: null,
    match_part_time_fit: null,
    match_scored_at: null,
    created_at: '2026-08-26T04:27:03Z',
    updated_at: '2026-08-26T04:27:03Z',
    application: null,
    ...overrides,
  }
}

function renderWithClient(ui: ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('Jobs page', () => {
  it('renders the Jobs heading', () => {
    renderWithClient(<Jobs />)
    expect(screen.getByRole('heading', { name: /jobs/i })).toBeDefined()
  })

  it('defaults the part-time scope filter to ON and queries with exclude_full_time', () => {
    renderWithClient(<Jobs />)
    const toggle = screen.getByRole('checkbox', { name: /part-time only/i }) as HTMLInputElement
    expect(toggle.checked).toBe(true)
    expect(vi.mocked(listJobs)).toHaveBeenCalledWith(
      expect.objectContaining({ exclude_full_time: true }),
    )
  })

  it('renders jobs returned by the API', async () => {
    renderWithClient(<Jobs />)
    expect(await screen.findByText(/React dashboard tweaks/i)).toBeDefined()
    expect(screen.getByText('React')).toBeDefined()
  })

  it('filters the visible jobs by source (client-side, no refetch)', async () => {
    vi.mocked(listJobs).mockResolvedValueOnce([
      makeJob({ id: 2, source: 'manual', title: 'Manual gig' }),
      makeJob({ id: 3, source: 'upwork', title: 'Upwork gig' }),
    ])
    renderWithClient(<Jobs />)

    // Both sources are visible before the source filter is touched.
    expect(await screen.findByText('Manual gig')).toBeDefined()
    expect(screen.getByText('Upwork gig')).toBeDefined()

    // Narrowing to Upwork drops the manual posting from the list.
    fireEvent.change(screen.getByLabelText(/source/i), { target: { value: 'upwork' } })
    expect(screen.queryByText('Manual gig')).toBeNull()
    expect(screen.getByText('Upwork gig')).toBeDefined()
  })
})
