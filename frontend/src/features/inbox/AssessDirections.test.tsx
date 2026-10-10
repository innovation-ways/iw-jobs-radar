import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { makeProfile } from '@/test/builders'
import { AssessDirections } from './AssessDirections'
import type { InboxDetail } from './queries'

const post = vi.fn()
const get = vi.fn()
vi.mock('@/api/client', () => ({
  api: { POST: (...args: unknown[]) => post(...args), GET: (...args: unknown[]) => get(...args) },
}))

type Dimension = InboxDetail['dimensions'][number]
const notAssessed: Dimension = {
  dimension_key: 'career_direction',
  status: 'unknown',
  quality: null,
  weight: 0,
  effective_weight: 0,
  strength: 0,
  contribution: 0,
  excluded: true,
  evidence: { reason: 'The job was not assessed against your career directions.' },
  explanation: 'The job was not assessed against your career directions.',
}

function withDirections(enabled = true) {
  const profile = makeProfile()
  profile.current_revision!.facts.directions = [
    { label: 'Billing SME', text: 'Telecom billing roles.', enabled },
  ]
  get.mockResolvedValue({ data: { items: [profile] }, response: { status: 200 } })
}

function renderIt(dimensions: Dimension[] = [notAssessed]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <AssessDirections jobPostingId={42} dimensions={dimensions} />
    </QueryClientProvider>,
  )
}

describe('AssessDirections', () => {
  beforeEach(() => {
    post.mockReset()
    get.mockReset()
  })

  it('offers to assess a job that was not assessed when a direction is enabled', async () => {
    withDirections()
    renderIt()
    post.mockResolvedValue({ data: { judged: 1, evaluated: 1 }, response: { status: 200 } })
    await userEvent.click(await screen.findByRole('button', { name: /assess this job/i }))
    expect(post).toHaveBeenCalledWith('/api/v1/jobs/{job_posting_id}/assess-directions', {
      params: { path: { job_posting_id: 42 } },
    })
    expect(await screen.findByText(/assessed: 1 direction judged/i)).toBeInTheDocument()
  })

  it('shows nothing without an enabled direction', async () => {
    withDirections(false)
    renderIt()
    await screen.findByText(/career direction/i, {}, { timeout: 200 }).catch(() => undefined)
    expect(screen.queryByRole('button', { name: /assess this job/i })).not.toBeInTheDocument()
  })

  it('shows nothing when the job was already assessed', async () => {
    withDirections()
    renderIt([{ ...notAssessed, excluded: false, evidence: { direction: 'Billing SME' } }])
    expect(screen.queryByRole('button', { name: /assess this job/i })).not.toBeInTheDocument()
  })

  it('says when the local model could not be reached', async () => {
    withDirections()
    post.mockRejectedValue(new Error('network'))
    renderIt()
    await userEvent.click(await screen.findByRole('button', { name: /assess this job/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not/i)
  })
})
