import type { ReactElement } from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import Dashboard from './Dashboard'

// Keep the smoke test hermetic: stub the API module so nothing hits the network.
vi.mock('../lib/api', () => ({
  getHealth: vi.fn().mockResolvedValue({ status: 'ok', db: true }),
}))

function renderWithClient(ui: ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>)
}

describe('Dashboard', () => {
  it('renders the dashboard heading', () => {
    renderWithClient(<Dashboard />)
    const heading = screen.getByRole('heading', { name: /dashboard/i })
    expect(heading).toBeDefined()
  })
})
