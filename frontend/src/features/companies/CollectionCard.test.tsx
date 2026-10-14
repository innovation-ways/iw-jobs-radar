import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { CollectionCard } from './CollectionCard'

const post = vi.fn()
const put = vi.fn()
vi.mock('@/api/client', () => ({
  api: {
    POST: (...a: unknown[]) => post(...a),
    PUT: (...a: unknown[]) => put(...a),
    GET: vi.fn(),
    DELETE: vi.fn(),
  },
}))

function board(overrides: Record<string, unknown> = {}) {
  return {
    source_configuration_id: 4,
    display_name: 'Synthco',
    enabled: true,
    url: 'https://synthco.example/careers',
    source_type: 'greenhouse',
    version: 2,
    last_outcome: 'success',
    last_error_class: null,
    last_finished_at: '2026-10-13T07:30:00Z',
    last_collected_count: 61,
    last_dropped_count: 0,
    filters_enabled: false,
    ...overrides,
  }
}

function setup(boards: unknown[], careers: string | null = 'https://synthco.example/careers') {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <CollectionCard
        name="Synthco"
        websiteUrl="https://synthco.example/"
        careersUrl={careers}
        boards={boards as never}
      />
    </QueryClientProvider>,
  )
  return userEvent.setup()
}

beforeEach(() => {
  post.mockReset()
  put.mockReset()
})

describe('CollectionCard', () => {
  it('says in words that a company without a source is not collected', () => {
    setup([])
    expect(screen.getByText('Not collected')).toBeInTheDocument()
    expect(screen.getByText(/No source collects/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Careers page' })).toHaveAttribute(
      'href',
      'https://synthco.example/careers',
    )
  })

  it('shows the source with its last result', () => {
    setup([board()])
    expect(screen.getByText('Collecting')).toBeInTheDocument()
    expect(screen.getByText('Greenhouse board')).toBeInTheDocument()
    expect(screen.getByText(/Last run succeeded · 61 postings/)).toBeInTheDocument()
  })

  it('reopens the dialog filled in for "Detect again"', async () => {
    const user = setup([])
    await user.click(screen.getByRole('button', { name: 'Detect again' }))
    expect(screen.getByLabelText(/company name/i)).toHaveValue('Synthco')
    expect(screen.getByLabelText(/careers page/i)).toHaveValue('https://synthco.example/careers')
  })

  it('offers a new reader when the page no longer matches the approved one', async () => {
    const proposal = {
      reader: { schema_version: 1, listing_url: 'https://synthco.example/careers' },
      preview: [{ title: 'Data Analyst', url: 'https://synthco.example/j/2', location: '' }],
      proposed_by: 'model:ollama:qwen3:14b:reader-v1',
    }
    post.mockResolvedValueOnce({ data: proposal })
    put.mockResolvedValueOnce({ data: {} })
    const user = setup([
      board({
        source_type: 'page_config',
        last_outcome: 'failed',
        last_error_class: 'schema_changed',
      }),
    ])
    expect(screen.getByText(/no longer matches the approved reader/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Propose a new reader' }))
    expect(await screen.findByText('Data Analyst')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Approve the new reader' }))
    await waitFor(() => expect(put).toHaveBeenCalled())
    expect(put.mock.calls[0][1].body).toMatchObject({
      expected_version: 2,
      proposed_by: proposal.proposed_by,
    })
  })

  it('says how many postings the filters left out and offers to turn them off', async () => {
    put.mockResolvedValue({ data: { source_configuration_id: 4 } })
    post.mockResolvedValue({ data: { collection_run_id: 9 } })
    const user = setup([
      board({
        source_type: 'page_jsonld',
        last_outcome: 'partial',
        last_collected_count: 0,
        last_dropped_count: 200,
        filters_enabled: true,
      }),
    ])
    expect(screen.getByText(/200 left out by your filters/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Turn off filters and collect/ }))
    await waitFor(() => expect(put).toHaveBeenCalled())
    expect(put.mock.calls[0][1].body).toEqual({ expected_version: 2, clear_filters: true })
    await waitFor(() => expect(post).toHaveBeenCalled())
    expect(post.mock.calls[0][0]).toBe('/api/v1/sources/{source_configuration_id}/run')
  })

  it('does not offer to turn filters off when they are not on', () => {
    setup([board({ last_dropped_count: 3, filters_enabled: false })])
    expect(screen.queryByRole('button', { name: /Turn off filters/ })).not.toBeInTheDocument()
  })
})
