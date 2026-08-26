import type { ReactElement } from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import Pipeline from './Pipeline'
import { updateApplication } from '../lib/api/applications'

// Stub the applications client so the test never hits the network. The fixture
// lives inside the factory: vi.mock is hoisted above the file, so it must not
// close over any top-level binding.
vi.mock('../lib/api/applications', () => {
  const sampleCard = {
    id: 1,
    status: 'saved',
    notes: null,
    applied_at: null,
    created_at: '2026-08-26T04:27:03Z',
    updated_at: '2026-08-26T04:27:03Z',
    job: {
      id: 1,
      source: 'manual',
      title: 'React dashboard tweaks (evenings)',
      url: 'https://www.upwork.com/jobs/~sample',
      budget_type: 'hourly',
      budget_min: 30,
      budget_max: 50,
      currency: 'USD',
      workload: 'part_time',
      weekly_hours: 10,
      duration: 'one_to_three_months',
    },
  }
  return {
    APPLICATION_STAGES: ['saved', 'applied', 'interviewing', 'offer', 'rejected'],
    STAGE_LABELS: {
      saved: 'Saved',
      applied: 'Applied',
      interviewing: 'Interviewing',
      offer: 'Offer',
      rejected: 'Rejected',
    },
    listApplications: vi.fn().mockResolvedValue([sampleCard]),
    updateApplication: vi.fn().mockResolvedValue(sampleCard),
    applicationsQueryKey: (filters = {}) => ['applications', filters],
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

describe('Pipeline page', () => {
  it('renders the Pipeline heading and all five stage columns', async () => {
    renderWithClient(<Pipeline />)
    expect(screen.getByRole('heading', { name: /^pipeline$/i })).toBeDefined()
    // Columns render once the board feed loads (the empty branch shows before).
    for (const label of ['Saved', 'Applied', 'Interviewing', 'Offer', 'Rejected']) {
      expect(await screen.findByRole('heading', { name: label })).toBeDefined()
    }
  })

  it('renders a card from the API with its job summary', async () => {
    renderWithClient(<Pipeline />)
    expect(await screen.findByText(/React dashboard tweaks/i)).toBeDefined()
  })

  it('moving a card via its stage menu PATCHes the new status', async () => {
    renderWithClient(<Pipeline />)
    await screen.findByText(/React dashboard tweaks/i)
    const select = screen.getByRole('combobox') as HTMLSelectElement
    fireEvent.change(select, { target: { value: 'applied' } })
    await waitFor(() =>
      expect(vi.mocked(updateApplication)).toHaveBeenCalledWith(1, { status: 'applied' }),
    )
  })

  it('editing notes PATCHes the note text', async () => {
    renderWithClient(<Pipeline />)
    await screen.findByText(/React dashboard tweaks/i)
    fireEvent.click(screen.getByRole('button', { name: /add notes/i }))
    const textarea = screen.getByLabelText(/card notes/i)
    fireEvent.change(textarea, { target: { value: 'Great evening fit' } })
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }))
    await waitFor(() =>
      expect(vi.mocked(updateApplication)).toHaveBeenCalledWith(1, { notes: 'Great evening fit' }),
    )
  })
})
