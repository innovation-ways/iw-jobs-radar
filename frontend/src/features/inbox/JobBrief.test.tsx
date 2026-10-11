import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { JobBrief } from './JobBrief'
import type { InboxDetail } from './queries'

const post = vi.fn()
vi.mock('@/api/client', () => ({ api: { POST: (...args: unknown[]) => post(...args) } }))

type Brief = InboxDetail['brief']
const written: Brief = {
  summary: 'Acme is hiring a senior engineer, fully remote.\n\nYou would build the rating engine.',
  summary_model: 'qwen3:8b',
  technologies: [
    { name: 'Java', importance: 'must' },
    { name: 'Kafka', importance: 'nice' },
  ],
  facts: ['Senior', '10+ years', 'Remote'],
}
const empty: Brief = { summary: null, summary_model: null, technologies: [], facts: [] }

function renderIt(brief: Brief) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <JobBrief brief={brief} jobPostingId={42} />
    </QueryClientProvider>,
  )
}

describe('JobBrief', () => {
  beforeEach(() => post.mockReset())

  it('shows the summary in paragraphs, labelled as an AI summary with its model', () => {
    renderIt(written)
    expect(screen.getByText(/acme is hiring a senior engineer/i)).toBeInTheDocument()
    expect(screen.getByText(/you would build the rating engine/i)).toBeInTheDocument()
    expect(screen.getByText(/ai summary/i)).toHaveAttribute(
      'title',
      expect.stringContaining('qwen3:8b'),
    )
    expect(screen.queryByRole('button', { name: /generate summary/i })).not.toBeInTheDocument()
  })

  it('says the summary has not been generated yet and offers to generate it', async () => {
    renderIt(empty)
    expect(screen.getByText(/the summary has not been generated yet/i)).toBeInTheDocument()
    post.mockResolvedValue({
      data: { summary: 'Written now, long enough.', created: true },
      response: { status: 200 },
    })
    await userEvent.click(screen.getByRole('button', { name: /generate summary/i }))
    expect(post).toHaveBeenCalledWith('/api/v1/jobs/{job_posting_id}/summary', {
      params: { path: { job_posting_id: 42 } },
    })
    expect(await screen.findByText(/written now, long enough/i)).toBeInTheDocument()
  })

  it('says when the local model could not write the summary (a 503 from the API)', async () => {
    post.mockResolvedValue({
      error: {
        error: { code: 'dependency_unavailable', message: 'The local model could not be reached.' },
      },
      response: { status: 503 },
    })
    renderIt(empty)
    await userEvent.click(screen.getByRole('button', { name: /generate summary/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not be reached/i)
    expect(screen.getByText(/the summary has not been generated yet/i)).toBeInTheDocument()
  })

  it('lists the key facts on one line', () => {
    renderIt(written)
    expect(screen.getByLabelText(/key facts/i)).toHaveTextContent('Senior · 10+ years · Remote')
  })

  it('shows technologies with required and preferred told apart by text, not only by style', () => {
    renderIt(written)
    const list = screen.getByRole('list', { name: /technologies/i })
    const items = within(list).getAllByRole('listitem')
    expect(items[0]).toHaveTextContent(/java/i)
    expect(items[0]).toHaveTextContent(/required/i)
    expect(items[1]).toHaveTextContent(/kafka/i)
    expect(items[1]).toHaveTextContent(/preferred/i)
  })

  it('shows the first eight technologies and the rest on request', async () => {
    const many = Array.from({ length: 11 }, (_, i) => ({
      name: `Tech${i + 1}`,
      importance: 'must' as const,
    }))
    renderIt({ ...written, technologies: many })
    expect(screen.getByText('Tech8')).toBeInTheDocument()
    expect(screen.queryByText('Tech9')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /\+3 more/i }))
    expect(screen.getByText('Tech11')).toBeInTheDocument()
  })

  it('leaves out technologies and facts when there are none', () => {
    renderIt(empty)
    expect(screen.queryByRole('list', { name: /technologies/i })).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/key facts/i)).not.toBeInTheDocument()
  })
})
