import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { PreApplication } from './PreApplication'

const get = vi.fn()
const post = vi.fn()
vi.mock('@/api/client', () => ({
  api: {
    GET: (...args: unknown[]) => get(...args),
    POST: (...args: unknown[]) => post(...args),
  },
}))

const draft = {
  application_draft_id: 7,
  created_at: '2026-10-12T20:00:00Z',
  model: 'qwen3.6:27b',
  prompt_version: 'application-v1',
  draft: {
    schema_version: 1,
    strengths: [
      { point: 'Deep Java experience', evidence: '10 years of Java' },
      { point: 'Billing domain', evidence: 'Rating engine at Nova Telecom' },
      { point: 'Database depth', evidence: 'PostgreSQL, advanced' },
    ],
    positioning: 'Introduce yourself as a billing-platform engineer.',
    gaps: ['Kubernetes is not shown in the profile.'],
    cover_letter: 'Dear team,\n\nI would like to apply.\n\n[Your name]',
    letter_language: 'en',
  },
}

function renderIt() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <PreApplication jobPostingId={42} />
    </QueryClientProvider>,
  )
}

describe('PreApplication', () => {
  beforeEach(() => {
    get.mockReset()
    post.mockReset()
  })

  it('offers the button when there is no draft yet and writes nothing by itself', async () => {
    get.mockResolvedValue({ data: { items: [] }, response: { status: 200 } })
    renderIt()
    expect(await screen.findByRole('button', { name: /pre-application/i })).toBeInTheDocument()
    expect(post).not.toHaveBeenCalled()
  })

  it('writes a draft on click and shows strengths, positioning, gaps and the letter', async () => {
    get.mockResolvedValue({ data: { items: [] }, response: { status: 200 } })
    post.mockResolvedValue({ data: draft, response: { status: 200 } })
    renderIt()
    await userEvent.click(await screen.findByRole('button', { name: /pre-application/i }))
    expect(post).toHaveBeenCalledWith('/api/v1/jobs/{job_posting_id}/application-draft', {
      params: { path: { job_posting_id: 42 } },
    })
    expect(await screen.findByText('Deep Java experience')).toBeInTheDocument()
    expect(screen.getByText(/10 years of java/i)).toBeInTheDocument()
    expect(
      screen.getByText(/introduce yourself as a billing-platform engineer/i),
    ).toBeInTheDocument()
    expect(screen.getByText(/kubernetes is not shown/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/cover letter/i)).toHaveTextContent(/i would like to apply/i)
    expect(screen.getByText(/check every claim/i)).toBeInTheDocument()
  })

  it('shows the newest stored draft and lets the owner write another', async () => {
    get.mockResolvedValue({ data: { items: [draft] }, response: { status: 200 } })
    renderIt()
    expect(await screen.findByText('Deep Java experience')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /write another/i })).toBeInTheDocument()
  })

  it('copies the cover letter', async () => {
    get.mockResolvedValue({ data: { items: [draft] }, response: { status: 200 } })
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    renderIt()
    await userEvent.click(await screen.findByRole('button', { name: /copy letter/i }))
    expect(writeText).toHaveBeenCalledWith(draft.draft.cover_letter)
    expect(await screen.findByText(/copied/i)).toBeInTheDocument()
  })

  it('says when the local model could not write the draft (a 503 from the API)', async () => {
    get.mockResolvedValue({ data: { items: [] }, response: { status: 200 } })
    post.mockResolvedValue({
      error: {
        error: { code: 'dependency_unavailable', message: 'The local model could not be reached.' },
      },
      response: { status: 503 },
    })
    renderIt()
    await userEvent.click(await screen.findByRole('button', { name: /pre-application/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not be reached/i)
  })
})
