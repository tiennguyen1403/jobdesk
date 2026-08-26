import type { ReactElement } from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import AiRuns from './AiRuns'
import { listAiRuns } from '../lib/api/aiRuns'

// Stub the ledger client so the test never hits the network. The fixture lives
// inside the factory: vi.mock is hoisted above the file, so it must not close
// over any top-level binding. KNOWN_AI_FEATURES is stubbed empty so the feature
// dropdown's <option>s don't collide with the sample rows' feature text.
vi.mock('../lib/api/aiRuns', () => {
  const runs = [
    {
      id: 2,
      feature: 'score_match',
      model: 'claude-3-5-haiku-latest',
      status: 'success',
      input_tokens: 1200,
      output_tokens: 180,
      cost_usd: 0.0123,
      error: null,
      job_id: 7,
      created_at: '2026-08-26T04:27:03Z',
    },
    {
      id: 1,
      feature: 'tailor_cv',
      model: 'claude-3-5-haiku-latest',
      status: 'error',
      input_tokens: 500,
      output_tokens: 0,
      cost_usd: 0.04,
      error: 'Anthropic API error: rate limit reached',
      job_id: 7,
      created_at: '2026-08-25T04:27:03Z',
    },
  ]
  return {
    listAiRuns: vi.fn().mockResolvedValue(runs),
    aiRunsQueryKey: (filters = {}) => ['ai-runs', filters],
    KNOWN_AI_FEATURES: [],
  }
})

function renderWithClient(ui: ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('AiRuns page', () => {
  it('renders the AI Runs heading', () => {
    renderWithClient(<AiRuns />)
    expect(screen.getByRole('heading', { name: /ai runs/i })).toBeDefined()
  })

  it('renders ledger rows returned by the API', async () => {
    renderWithClient(<AiRuns />)
    expect(await screen.findByText('score_match')).toBeDefined()
    expect(screen.getByText('$0.0123')).toBeDefined()
  })

  it('surfaces the error text on failed runs', async () => {
    renderWithClient(<AiRuns />)
    expect(await screen.findByText(/rate limit reached/i)).toBeDefined()
  })

  it('queries the ledger through the API client', async () => {
    renderWithClient(<AiRuns />)
    await screen.findByText('score_match')
    expect(vi.mocked(listAiRuns)).toHaveBeenCalled()
  })
})
