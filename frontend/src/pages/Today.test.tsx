import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { makeItem } from '@/test/inboxBuilders'
import { Today } from './Today'

const get = vi.fn()
vi.mock('@/api/client', () => ({ api: { GET: (...args: unknown[]) => get(...args) } }))

function digest(overrides: Record<string, unknown> = {}) {
  return {
    generated_at: '2026-10-08T09:00:00Z',
    since: '2026-10-07T09:00:00Z',
    search_intent_id: 2,
    alert_threshold: 65,
    new_high_fit: [makeItem({ title: 'Staff ML Engineer' })],
    changed_shortlisted: [
      {
        item: makeItem({ title: 'Platform Lead', is_shortlisted: true }),
        changed_fields: ['title', 'description'],
        changed_at: '2026-10-08T08:00:00Z',
      },
    ],
    source_health: [
      {
        source_configuration_id: 3,
        display_name: 'Contoso',
        status: 'failed',
        error_class: 'not_found',
        error_message: 'The board was not found.',
        last_run_at: '2026-10-08T07:30:00Z',
      },
      {
        source_configuration_id: 4,
        display_name: 'Globex',
        status: 'never_run',
        error_class: null,
        error_message: null,
        last_run_at: null,
      },
    ],
    last_run: null,
    counts: { new_high_fit: 1, changed_shortlisted: 1, sources_needing_attention: 2 },
    ...overrides,
  }
}

function renderToday() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <Today />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('Today screen', () => {
  beforeEach(() => {
    get.mockReset()
    get.mockResolvedValue({ data: digest() })
  })

  it('shows the three sections with counts', async () => {
    renderToday()
    const fresh = (await screen.findByRole('heading', { name: /New matches/ })).closest('section')!
    expect(within(fresh).getByText('Staff ML Engineer')).toBeInTheDocument()
    expect(within(fresh).getByText(/65 or higher/)).toBeInTheDocument()
    const changed = screen
      .getByRole('heading', { name: /Shortlisted jobs that changed/ })
      .closest('section')!
    expect(within(changed).getByText('Platform Lead')).toBeInTheDocument()
    expect(within(changed).getByText(/title, description/)).toBeInTheDocument()
    const health = screen
      .getByRole('heading', { name: /Sources needing attention/ })
      .closest('section')!
    expect(within(health).getByText(/Contoso/)).toBeInTheDocument()
    expect(within(health).getByText(/board was not found/i)).toBeInTheDocument()
    expect(within(health).getByText(/Never run/)).toBeInTheDocument()
  })

  it('links a changed job to its own item in the shortlist', async () => {
    renderToday()
    const link = await screen.findByRole('link', { name: /Platform Lead/ })
    const params = new URL(link.getAttribute('href')!, 'http://x').searchParams
    expect(params.get('tab')).toBe('shortlist')
    expect(params.get('item')).toMatch(/^\d+$/)
  })

  it('links each job to the inbox', async () => {
    renderToday()
    const link = await screen.findByRole('link', { name: /Staff ML Engineer/ })
    expect(link).toHaveAttribute('href', '/inbox')
  })

  it('says so when there is nothing new', async () => {
    get.mockResolvedValue({
      data: digest({
        new_high_fit: [],
        changed_shortlisted: [],
        source_health: [],
        counts: { new_high_fit: 0, changed_shortlisted: 0, sources_needing_attention: 0 },
      }),
    })
    renderToday()
    expect(await screen.findByText(/nothing new in the last 24 hours/i)).toBeInTheDocument()
    expect(screen.getByText(/all sources are healthy/i)).toBeInTheDocument()
  })

  it('reports a failed load and lets the owner retry', async () => {
    get.mockRejectedValueOnce(new Error('down'))
    renderToday()
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not load/i)
  })
})
