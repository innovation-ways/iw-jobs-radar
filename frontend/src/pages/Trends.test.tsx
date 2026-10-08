import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Trends } from './Trends'

const get = vi.fn()
vi.mock('@/api/client', () => ({ api: { GET: (...a: unknown[]) => get(...a) } }))

function report(kind: string, overrides: Record<string, unknown> = {}) {
  const weeks = ['2026-09-14', '2026-09-21', '2026-09-28', '2026-10-05']
  return {
    kind,
    search_intent_id: 1,
    relevance_min_score: 45,
    available_weeks: 4,
    first_week: '2026-09-14',
    periods: [
      { key: '4w', weeks: 4, available: true },
      { key: '12w', weeks: 12, available: false },
      { key: '6m', weeks: 26, available: false },
    ],
    weeks: weeks.map((w) => ({ week_start: w, relevant_total_open: 10, intent_revision_id: 3 })),
    rows: [
      {
        term_key: 'python',
        label: 'Python',
        open_now: 6,
        share_now: 0.6,
        share_change: 0.2,
        count_change: 3,
        series: weeks.map((w, i) => ({ week_start: w, open_count: 3 + i, share: 0.4 + i * 0.07 })),
      },
      {
        term_key: 'sql',
        label: 'SQL',
        open_now: 2,
        share_now: 0.2,
        share_change: -0.1,
        count_change: -1,
        series: weeks.map((w) => ({ week_start: w, open_count: 2, share: 0.2 })),
      },
    ],
    intent_revision_changes: [],
    source_set_changes: [],
    ...overrides,
  }
}

let current: (kind: string) => Record<string, unknown>

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <Trends />
    </QueryClientProvider>,
  )
}

describe('Trends screen', () => {
  beforeEach(() => {
    get.mockReset()
    current = (kind) => report(kind)
    get.mockImplementation((_path: string, options: { params: { query: { kind: string } } }) =>
      Promise.resolve({ data: current(options.params.query.kind) }),
    )
  })

  it('ranks terms with their share, a change in words and a sparkline', async () => {
    renderPage()
    const table = await screen.findByRole('table', { name: 'Technologies' })
    const python = within(table).getByRole('row', { name: /Python/ })
    expect(within(python).getByText('60%')).toBeInTheDocument()
    expect(within(python).getByText(/\+20 pts/)).toBeInTheDocument()
    expect(within(python).getByRole('img', { name: /Python.*share/i })).toBeInTheDocument()
    const sql = within(table).getByRole('row', { name: /SQL/ })
    expect(within(sql).getByText(/−10 pts/)).toBeInTheDocument()
  })

  it('states the history that exists and keeps longer periods locked', async () => {
    renderPage()
    expect(await screen.findByText(/History available:/)).toHaveTextContent(/4 weeks \(from/)
    expect(screen.getByRole('button', { name: '4 weeks' })).toBeEnabled()
    const twelve = screen.getByRole('button', { name: '12 weeks' })
    expect(twelve).toBeDisabled()
    expect(twelve).toHaveAttribute('title', expect.stringMatching(/unlocks/i))
    expect(screen.getByRole('button', { name: '6 months' })).toBeDisabled()
  })

  it('asks for the chosen period', async () => {
    const user = userEvent.setup()
    current = (kind) =>
      report(kind, {
        available_weeks: 12,
        periods: [
          { key: '4w', weeks: 4, available: true },
          { key: '12w', weeks: 12, available: true },
          { key: '6m', weeks: 26, available: false },
        ],
      })
    renderPage()
    await screen.findByRole('table', { name: 'Technologies' })
    await user.click(screen.getByRole('button', { name: '4 weeks' }))
    const last = get.mock.calls.at(-1)![1]
    expect(last.params.query.weeks).toBe(4)
  })

  it('explains changes of the intent and of the sources', async () => {
    current = (kind) =>
      report(kind, { intent_revision_changes: ['2026-09-28'], source_set_changes: ['2026-10-05'] })
    renderPage()
    expect(await screen.findAllByText(/your search intent changed/i)).not.toHaveLength(0)
    expect(screen.getAllByText(/sources changed/i).length).toBeGreaterThan(0)
  })

  it('shows the relevance threshold and explains an empty period', async () => {
    current = (kind) => report(kind, { rows: [], available_weeks: 0, first_week: null, weeks: [] })
    renderPage()
    expect(await screen.findAllByText(/no relevant jobs yet/i)).not.toHaveLength(0)
    expect(screen.getByText(/fit of 45 or higher/i)).toBeInTheDocument()
  })

  it('tells the owner to create an intent when there is none', async () => {
    get.mockResolvedValue({
      error: {
        error: {
          code: 'not_found',
          message: 'Create a search intent first: trends cover the jobs that are relevant to it.',
          details: {},
        },
      },
      response: { status: 404 },
    })
    renderPage()
    expect(await screen.findByText(/create a search intent first/i)).toBeInTheDocument()
  })
})
