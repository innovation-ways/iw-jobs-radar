import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { FollowCompanyDialog } from './FollowCompanyDialog'

const post = vi.fn()
vi.mock('@/api/client', () => ({
  api: { POST: (...a: unknown[]) => post(...a), GET: vi.fn(), PUT: vi.fn(), DELETE: vi.fn() },
}))

const board = {
  source_type: 'ashby',
  identifier: 'mistral.ai',
  display_name: 'Mistral AI',
  postings_count: 213,
  layer: 'ats',
}

function detection(overrides: Record<string, unknown> = {}) {
  return {
    outcome: 'detected',
    website_url: 'https://mistral.ai/',
    careers_url: 'https://jobs.ashbyhq.com/mistral.ai',
    candidates: [board],
    reason: null,
    existing_company_id: null,
    ...overrides,
  }
}

function setup(onDone = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <FollowCompanyDialog onClose={vi.fn()} onDone={onDone} />
    </QueryClientProvider>,
  )
  return { onDone, user: userEvent.setup() }
}

async function fill(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText(/company name/i), 'Mistral AI')
  await user.type(screen.getByLabelText(/company website/i), 'https://mistral.ai')
  await user.type(screen.getByLabelText(/careers page/i), 'https://jobs.ashbyhq.com/mistral.ai')
}

beforeEach(() => post.mockReset())

describe('FollowCompanyDialog', () => {
  it('asks for the three required fields before checking anything', async () => {
    const { user } = setup()
    await user.click(screen.getByRole('button', { name: 'Check addresses' }))
    expect(screen.getByText('Enter the company name.')).toBeInTheDocument()
    expect(screen.getByText('Enter the company website.')).toBeInTheDocument()
    expect(screen.getByText('Enter the careers page address.')).toBeInTheDocument()
    expect(post).not.toHaveBeenCalled()
  })

  it('has the area and location filter on by default and confirmation disabled until a check', () => {
    setup()
    expect(screen.getByRole('checkbox')).toBeChecked()
    expect(screen.getByRole('button', { name: 'Follow without collection' })).toBeDisabled()
  })

  it('follows a detected board, collects it now and reports the company', async () => {
    post.mockResolvedValueOnce({ data: detection() }).mockResolvedValueOnce({
      data: {
        company_id: 7,
        company_name: 'Mistral AI',
        is_followed: true,
        source_configuration_id: 3,
        collection_run_id: 9,
        collecting: true,
      },
    })
    const { user, onDone } = setup()
    await fill(user)
    await user.click(screen.getByRole('button', { name: 'Check addresses' }))
    expect(await screen.findByText('Found a source to collect from')).toBeInTheDocument()
    expect(screen.getByText(/213 open postings/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Follow and collect now' }))
    await waitFor(() => expect(onDone).toHaveBeenCalledWith(7))
    const [path, init] = post.mock.calls[1]
    expect(path).toBe('/api/v1/companies/onboarding')
    expect(init.body).toMatchObject({
      name: 'Mistral AI',
      filters_enabled: true,
      source: { source_type: 'ashby', identifier: 'mistral.ai' },
    })
  })

  it('lets the owner choose between several boards', async () => {
    const other = { ...board, source_type: 'greenhouse', identifier: 'mistral', postings_count: 4 }
    post
      .mockResolvedValueOnce({
        data: detection({ outcome: 'ambiguous', candidates: [board, other] }),
      })
      .mockResolvedValueOnce({ data: { company_id: 1, collecting: true } })
    const { user } = setup()
    await fill(user)
    await user.click(screen.getByRole('button', { name: 'Check addresses' }))
    await user.click(await screen.findByRole('radio', { name: /Greenhouse board/ }))
    await user.click(screen.getByRole('button', { name: 'Follow and collect now' }))
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2))
    expect(post.mock.calls[1][1].body.source).toEqual({
      source_type: 'greenhouse',
      identifier: 'mistral',
    })
  })

  it('offers to follow without collection when nothing can be collected', async () => {
    post
      .mockResolvedValueOnce({
        data: detection({ outcome: 'script_only', candidates: [], reason: 'Loaded by scripts.' }),
      })
      .mockResolvedValueOnce({ data: { company_id: 2, collecting: false } })
    const { user, onDone } = setup()
    await fill(user)
    await user.click(screen.getByRole('button', { name: 'Check addresses' }))
    expect(await screen.findByText('The postings are loaded by JavaScript')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Propose a reader' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Follow without collection' }))
    await waitFor(() => expect(onDone).toHaveBeenCalledWith(2))
    expect(post.mock.calls[1][1].body.source).toBeUndefined()
  })

  it('previews a model-proposed reader and sends it only once approved', async () => {
    const proposal = {
      reader: { schema_version: 1, listing_url: 'https://x.example/careers', item_selector: 'li' },
      preview: [{ title: 'Platform Engineer', url: 'https://x.example/j/1', location: 'Lisbon' }],
      proposed_by: 'model:ollama:qwen3:14b:reader-v1',
    }
    post
      .mockResolvedValueOnce({
        data: detection({ outcome: 'unsupported', candidates: [], reason: 'No known system.' }),
      })
      .mockResolvedValueOnce({ data: proposal })
      .mockResolvedValueOnce({ data: { company_id: 5, collecting: true } })
    const { user, onDone } = setup()
    await fill(user)
    await user.click(screen.getByRole('button', { name: 'Check addresses' }))
    await user.click(await screen.findByRole('button', { name: 'Propose a reader' }))
    expect(await screen.findByText('Platform Engineer')).toBeInTheDocument()
    expect(post).toHaveBeenCalledTimes(2) // nothing has been saved yet

    await user.click(screen.getByRole('button', { name: 'Approve reader and follow' }))
    await waitFor(() => expect(onDone).toHaveBeenCalledWith(5))
    expect(post.mock.calls[2][1].body).toMatchObject({
      reader: proposal.reader,
      reader_proposed_by: proposal.proposed_by,
    })
  })

  it('shows why the local model could not propose a reader', async () => {
    post
      .mockResolvedValueOnce({ data: detection({ outcome: 'unsupported', candidates: [] }) })
      .mockResolvedValueOnce({
        error: { error: { message: 'Choose a local model for job analysis in AI & privacy.' } },
      })
    const { user } = setup()
    await fill(user)
    await user.click(screen.getByRole('button', { name: 'Check addresses' }))
    await user.click(await screen.findByRole('button', { name: 'Propose a reader' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Choose a local model')
  })

  it('does not allow confirming a company that is already followed', async () => {
    post.mockResolvedValueOnce({ data: detection({ outcome: 'already_followed' }) })
    const { user } = setup()
    await fill(user)
    await user.click(screen.getByRole('button', { name: 'Check addresses' }))
    expect(await screen.findByText('This company is already followed')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Follow/ })).toBeDisabled()
  })
})
