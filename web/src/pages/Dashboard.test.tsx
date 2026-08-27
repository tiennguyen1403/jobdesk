import type { ReactElement } from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import Dashboard from './Dashboard'
import { getAnalyticsSummary } from '../lib/api/analytics'

// Keep the smoke test hermetic: stub both API modules so nothing hits the network.
// The health strip is stubbed healthy; the analytics fixture lives inside the
// factory (vi.mock is hoisted above the file, so it must not close over any
// top-level binding) and exercises every panel with non-zero, distinct numbers.
vi.mock('../lib/api', () => ({
  getHealth: vi.fn().mockResolvedValue({ status: 'ok', db: true }),
}))

vi.mock('../lib/api/analytics', () => {
  const summary = {
    jobs: {
      total: 42,
      by_source: { manual: 10, capture: 7, upwork: 20, freelancer: 5 },
    },
    match: {
      scored: 30,
      unscored: 12,
      part_time_fit: 18,
      bands: { low: 5, medium: 10, high: 15 },
    },
    pipeline: {
      total: 12,
      by_status: { saved: 4, applied: 3, interviewing: 2, offer: 1, rejected: 2 },
      applied_conversion: 0.6667,
    },
    ai: {
      total_cost_usd: 1.2345,
      input_tokens: 50000,
      output_tokens: 8000,
      by_feature: [
        { feature: 'score_match', cost_usd: 0.9, input_tokens: 40000, output_tokens: 5000, runs: 20 },
        { feature: 'tailor_cv', cost_usd: 0.3345, input_tokens: 10000, output_tokens: 3000, runs: 4 },
      ],
      days: 30,
      recent: [
        { date: '2026-08-25', cost_usd: 0.5, input_tokens: 20000, output_tokens: 3000, runs: 8 },
        { date: '2026-08-26', cost_usd: 0.7345, input_tokens: 30000, output_tokens: 5000, runs: 16 },
      ],
    },
  }
  return {
    getAnalyticsSummary: vi.fn().mockResolvedValue(summary),
    analyticsSummaryQueryKey: (days?: number) => ['analytics-summary', days],
  }
})

function renderWithClient(ui: ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>)
}

describe('Dashboard', () => {
  it('renders the dashboard heading', () => {
    renderWithClient(<Dashboard />)
    expect(screen.getByRole('heading', { name: /dashboard/i })).toBeDefined()
  })

  it('renders the analytics overview from the summary payload', async () => {
    renderWithClient(<Dashboard />)
    // Headline figures.
    expect(await screen.findByText('42')).toBeDefined() // total jobs
    expect(screen.getByText('$1.2345')).toBeDefined() // AI total spend
    expect(screen.getByText(/67% applied/)).toBeDefined() // applied conversion
    // Each panel rendered a labelled row.
    expect(screen.getByText('Upwork')).toBeDefined() // source mix
    expect(screen.getByText('Interviewing')).toBeDefined() // pipeline funnel
    expect(screen.getByText(/High \(70/)).toBeDefined() // match bands
    expect(screen.getByText(/score_match/)).toBeDefined() // AI spend by feature
  })

  it('renders zeros cleanly for an empty database', async () => {
    vi.mocked(getAnalyticsSummary).mockResolvedValueOnce({
      jobs: { total: 0, by_source: { manual: 0, capture: 0, upwork: 0, freelancer: 0 } },
      match: { scored: 0, unscored: 0, part_time_fit: 0, bands: { low: 0, medium: 0, high: 0 } },
      pipeline: { total: 0, by_status: {}, applied_conversion: 0 },
      ai: { total_cost_usd: 0, input_tokens: 0, output_tokens: 0, by_feature: [], days: 30, recent: [] },
    })
    renderWithClient(<Dashboard />)
    // Empty states render instead of crashing on divide-by-zero.
    expect(await screen.findByText(/no jobs yet/i)).toBeDefined()
    expect(screen.getByText(/no applications tracked yet/i)).toBeDefined()
    expect(screen.getByText(/no ai runs logged yet/i)).toBeDefined()
  })

  it('queries the analytics summary endpoint', async () => {
    renderWithClient(<Dashboard />)
    await screen.findByText('42')
    expect(vi.mocked(getAnalyticsSummary)).toHaveBeenCalled()
  })
})
