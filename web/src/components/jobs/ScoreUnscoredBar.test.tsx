import type { ReactElement } from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import ScoreUnscoredBar from './ScoreUnscoredBar'
import { getAnalyticsSummary } from '../../lib/api/analytics'
import { scoreUnscored } from '../../lib/api/jobs'

// Stub the two clients the bar reads. Fixtures live inside the factories (vi.mock
// is hoisted, so they must not close over any top-level binding).
vi.mock('../../lib/api/analytics', () => ({
  getAnalyticsSummary: vi.fn().mockResolvedValue({
    jobs: { total: 3, by_source: {} },
    match: { scored: 0, unscored: 3, part_time_fit: 0, bands: { low: 0, medium: 0, high: 0 } },
    pipeline: { total: 0, by_status: {}, applied_conversion: 0 },
    ai: { total_cost_usd: 0, input_tokens: 0, output_tokens: 0, by_feature: [], days: 30, recent: [] },
  }),
  analyticsSummaryQueryKey: (days?: number) => ['analytics-summary', days],
}))

vi.mock('../../lib/api/jobs', () => ({
  scoreUnscored: vi.fn().mockResolvedValue({
    scored: 3,
    failed: 0,
    remaining_unscored: 0,
    total_cost_usd: 0.0123,
    run_ids: [1, 2, 3],
  }),
}))

function renderBar(ui: ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>)
}

describe('ScoreUnscoredBar', () => {
  it('reveals a confirm step, then batch-scores with the cost-cap limit', async () => {
    renderBar(<ScoreUnscoredBar />)

    // The reveal button appears once analytics reports unscored jobs.
    const reveal = await screen.findByRole('button', { name: /score unscored/i })
    fireEvent.click(reveal)

    // A confirm step surfaces — this is a paid action.
    expect(screen.getByText(/paid AI call/i)).toBeDefined()

    // Confirming runs the batch, capped at BATCH_LIMIT (25).
    fireEvent.click(screen.getByRole('button', { name: /^score 3$/i }))
    await waitFor(() => expect(vi.mocked(scoreUnscored)).toHaveBeenCalledWith(25))

    // The outcome summary renders.
    expect(await screen.findByText(/Scored 3/)).toBeDefined()
  })

  it('renders nothing when there are no unscored jobs', async () => {
    vi.mocked(getAnalyticsSummary).mockResolvedValueOnce({
      jobs: { total: 1, by_source: {} },
      match: { scored: 1, unscored: 0, part_time_fit: 0, bands: { low: 0, medium: 0, high: 0 } },
      pipeline: { total: 0, by_status: {}, applied_conversion: 0 },
      ai: { total_cost_usd: 0, input_tokens: 0, output_tokens: 0, by_feature: [], days: 30, recent: [] },
    })

    const { container } = renderBar(<ScoreUnscoredBar />)
    await waitFor(() => expect(container.textContent).toBe(''))
  })
})
