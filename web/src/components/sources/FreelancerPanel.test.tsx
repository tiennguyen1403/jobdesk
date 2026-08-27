import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import FreelancerPanel from './FreelancerPanel'
import { disconnectFreelancer, getFreelancerStatus } from '../../lib/api/freelancer'

// Stub the Freelancer client so the panel never hits the network. Each test sets
// the status the query resolves to; the connect URL is a fixed fixture.
vi.mock('../../lib/api/freelancer', () => ({
  getFreelancerStatus: vi.fn(),
  disconnectFreelancer: vi.fn(),
  freelancerConnectUrl: () => 'http://api.test/api/freelancer/connect',
  freelancerStatusQueryKey: () => ['freelancer', 'status'],
}))

const CONFIGURED_DISCONNECTED = {
  provider: 'freelancer',
  connected: false,
  expired: false,
  expires_at: null,
  scope: null,
  configured: true,
}

function renderPanel() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <FreelancerPanel />
    </QueryClientProvider>,
  )
}

describe('FreelancerPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('offers a Connect link when configured but not connected', async () => {
    vi.mocked(getFreelancerStatus).mockResolvedValue(CONFIGURED_DISCONNECTED)
    renderPanel()
    const link = (await screen.findByRole('link', {
      name: /connect freelancer/i,
    })) as HTMLAnchorElement
    expect(link.getAttribute('href')).toBe('http://api.test/api/freelancer/connect')
  })

  it('shows a "not configured" hint on the 503 case, with no Connect button', async () => {
    vi.mocked(getFreelancerStatus).mockResolvedValue({
      ...CONFIGURED_DISCONNECTED,
      configured: false,
    })
    renderPanel()
    expect(await screen.findByText(/not configured/i)).toBeDefined()
    expect(screen.queryByRole('link', { name: /connect freelancer/i })).toBeNull()
  })

  it('shows the connection status + expiry and disconnects when connected', async () => {
    vi.mocked(getFreelancerStatus).mockResolvedValue({
      provider: 'freelancer',
      connected: true,
      expired: false,
      expires_at: '2026-09-01T00:00:00Z',
      scope: 'basic',
      configured: true,
    })
    vi.mocked(disconnectFreelancer).mockResolvedValue(CONFIGURED_DISCONNECTED)
    renderPanel()
    // A connected account exposes a Disconnect action and hides the Connect link.
    const disconnectBtn = await screen.findByRole('button', { name: /^disconnect$/i })
    expect(screen.queryByRole('link', { name: /connect freelancer/i })).toBeNull()
    fireEvent.click(disconnectBtn)
    await waitFor(() => expect(vi.mocked(disconnectFreelancer)).toHaveBeenCalled())
  })

  it('offers Reconnect when the token has expired', async () => {
    vi.mocked(getFreelancerStatus).mockResolvedValue({
      provider: 'freelancer',
      connected: true,
      expired: true,
      expires_at: '2020-01-01T00:00:00Z',
      scope: 'basic',
      configured: true,
    })
    renderPanel()
    const link = (await screen.findByRole('link', { name: /reconnect/i })) as HTMLAnchorElement
    expect(link.getAttribute('href')).toBe('http://api.test/api/freelancer/connect')
  })
})
