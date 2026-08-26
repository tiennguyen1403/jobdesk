import type { ReactElement } from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import JobCard from './JobCard'
import type { Application, Job } from '../../lib/api/jobs'

/** A complete Job with sensible defaults; override only what a test cares about. */
function makeJob(overrides: Partial<Job> = {}): Job {
  return {
    id: 1,
    source: 'upwork',
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

const savedCard: Application = {
  id: 5,
  status: 'saved',
  notes: null,
  applied_at: null,
  created_at: '2026-08-26T04:27:03Z',
  updated_at: '2026-08-26T04:27:03Z',
}

function renderCard(ui: ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>)
}

describe('JobCard', () => {
  it('shows a readable source badge for the job source', () => {
    renderCard(<JobCard job={makeJob({ source: 'upwork' })} />)
    expect(screen.getByText('Upwork')).toBeDefined()
  })

  it('falls back to the raw source for an unknown provider', () => {
    renderCard(<JobCard job={makeJob({ source: 'freelancer' })} />)
    expect(screen.getByText('freelancer')).toBeDefined()
  })

  it('offers "Add to pipeline" for an ingested job with no card and fires the handler', () => {
    const onAdd = vi.fn()
    renderCard(<JobCard job={makeJob({ application: null })} onAddToPipeline={onAdd} />)
    fireEvent.click(screen.getByRole('button', { name: /add to pipeline/i }))
    expect(onAdd).toHaveBeenCalledTimes(1)
  })

  it('hides "Add to pipeline" once the job is already in the pipeline', () => {
    renderCard(<JobCard job={makeJob({ application: savedCard })} onAddToPipeline={vi.fn()} />)
    expect(screen.queryByRole('button', { name: /add to pipeline/i })).toBeNull()
  })
})
