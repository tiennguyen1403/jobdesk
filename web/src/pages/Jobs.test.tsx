import type { ReactElement } from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import Jobs from './Jobs'
import { listJobs } from '../lib/api/jobs'

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
    jobsQueryKey: (filters = {}) => ['jobs', filters],
  }
})

function renderWithClient(ui: ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>)
}

describe('Jobs page', () => {
  it('renders the Jobs heading', () => {
    renderWithClient(<Jobs />)
    expect(screen.getByRole('heading', { name: /jobs/i })).toBeDefined()
  })

  it('defaults the part-time scope filter to ON and queries with workload=part_time', () => {
    renderWithClient(<Jobs />)
    const toggle = screen.getByRole('checkbox', { name: /part-time only/i }) as HTMLInputElement
    expect(toggle.checked).toBe(true)
    expect(vi.mocked(listJobs)).toHaveBeenCalledWith(
      expect.objectContaining({ workload: 'part_time' }),
    )
  })

  it('renders jobs returned by the API', async () => {
    renderWithClient(<Jobs />)
    expect(await screen.findByText(/React dashboard tweaks/i)).toBeDefined()
    expect(screen.getByText('React')).toBeDefined()
  })
})
