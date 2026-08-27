import type { ReactElement } from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, useSearchParams } from 'react-router-dom'
import Sources from './Sources'
import { getUpworkStatus } from '../lib/api/upwork'
import { createSavedSearch, listSavedSearches, runSavedSearch } from '../lib/api/savedSearches'

// Stub both API clients so the test never hits the network. Fixtures live inside
// the factories: vi.mock is hoisted above the file, so they must not close over
// any top-level binding. Defaults model a configured-but-not-connected Upwork and
// a single saved search.
vi.mock('../lib/api/upwork', () => ({
  getUpworkStatus: vi.fn().mockResolvedValue({
    provider: 'upwork',
    connected: false,
    expired: false,
    expires_at: null,
    scope: null,
    configured: true,
  }),
  disconnectUpwork: vi.fn(),
  upworkConnectUrl: () => 'http://api.test/api/upwork/connect',
  upworkStatusQueryKey: () => ['upwork', 'status'],
}))

vi.mock('../lib/api/savedSearches', () => {
  const searches = [
    {
      id: 1,
      name: 'Evening React gigs',
      provider: 'upwork',
      query: {
        keywords: 'react',
        category: 'Web Development',
        workload: 'part_time',
        max_weekly_hours: 20,
      },
      enabled: true,
      last_polled_at: null,
      created_at: '2026-08-26T04:27:03Z',
      updated_at: '2026-08-26T04:27:03Z',
    },
  ]
  return {
    listSavedSearches: vi.fn().mockResolvedValue(searches),
    createSavedSearch: vi.fn().mockResolvedValue(searches[0]),
    updateSavedSearch: vi.fn(),
    deleteSavedSearch: vi.fn().mockResolvedValue(undefined),
    runSavedSearch: vi.fn().mockResolvedValue({
      search_id: 1,
      provider: 'upwork',
      created: 3,
      updated: 1,
      skipped: 0,
      job_ids: [10, 11, 12],
      last_polled_at: '2026-08-27T09:00:00Z',
    }),
    savedSearchesQueryKey: (filters = {}) => ['saved-searches', filters],
  }
})

// Surfaces the live `upwork` query param so a test can assert the OAuth params
// were stripped from the URL after the banner rendered. '∅' = param absent.
function UpworkParamProbe() {
  const [params] = useSearchParams()
  return <span data-testid="upwork-param">{params.get('upwork') ?? '∅'}</span>
}

function renderPage(
  ui: ReactElement = <Sources />,
  { initialEntries = ['/sources'] }: { initialEntries?: string[] } = {},
) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={initialEntries}>
        {ui}
        <UpworkParamProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('Sources page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the Sources heading', () => {
    renderPage()
    expect(screen.getByRole('heading', { name: /sources/i })).toBeDefined()
  })

  it('offers a Connect link to the OAuth flow when configured but not connected', async () => {
    renderPage()
    const link = (await screen.findByRole('link', { name: /connect upwork/i })) as HTMLAnchorElement
    expect(link.getAttribute('href')).toBe('http://api.test/api/upwork/connect')
  })

  it('shows a clear "not configured" state on the 503 case', async () => {
    vi.mocked(getUpworkStatus).mockResolvedValueOnce({
      provider: 'upwork',
      connected: false,
      expired: false,
      expires_at: null,
      scope: null,
      configured: false,
    })
    renderPage()
    expect(await screen.findByText(/not configured/i)).toBeDefined()
    // With credentials absent there is no Connect button to click.
    expect(screen.queryByRole('link', { name: /connect upwork/i })).toBeNull()
  })

  it('lists saved searches returned by the API', async () => {
    renderPage()
    expect(await screen.findByText('Evening React gigs')).toBeDefined()
    expect(vi.mocked(listSavedSearches)).toHaveBeenCalled()
  })

  it('runs a saved search now and shows the ingest result', async () => {
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: /run now/i }))
    await waitFor(() => expect(vi.mocked(runSavedSearch)).toHaveBeenCalledWith(1))
    expect(await screen.findByText(/3 jobs touched/i)).toBeDefined()
  })

  it('creates a part-time-scoped saved search from the form', async () => {
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: /new search/i }))
    fireEvent.change(screen.getByLabelText(/name/i), { target: { value: 'Weekend Vue' } })
    fireEvent.click(screen.getByRole('button', { name: /create search/i }))
    await waitFor(() =>
      expect(vi.mocked(createSavedSearch)).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'Weekend Vue',
          query: expect.objectContaining({ workload: 'part_time' }),
        }),
      ),
    )
  })

  it('shows a success banner and strips the param after ?upwork=connected', async () => {
    renderPage(<Sources />, { initialEntries: ['/sources?upwork=connected'] })
    expect(await screen.findByText(/upwork connected/i)).toBeDefined()
    // The OAuth param is removed so a refresh/back-button won't re-show the banner.
    await waitFor(() => expect(screen.getByTestId('upwork-param').textContent).toBe('∅'))
  })

  it('shows a reason-derived error banner and strips the param on ?upwork=error', async () => {
    renderPage(<Sources />, { initialEntries: ['/sources?upwork=error&reason=denied'] })
    expect(await screen.findByText(/declined the upwork authorization/i)).toBeDefined()
    await waitFor(() => expect(screen.getByTestId('upwork-param').textContent).toBe('∅'))
  })
})
