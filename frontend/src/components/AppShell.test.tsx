import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import { AppRoutes } from '@/AppRoutes'
import { ThemeProvider } from '@/theme/ThemeProvider'

// Every screen is rendered by these tests; each endpoint answers in its own shape.
vi.mock('@/api/client', () => ({
  api: {
    GET: vi.fn((path: string) => {
      if (path === '/readyz') {
        return Promise.resolve({
          data: { status: 'ready', components: { database: 'up', worker: 'up' } },
          response: { status: 200 },
        })
      }
      if (path === '/api/v1/digests/daily') {
        return Promise.resolve({
          data: {
            counts: { new_high_fit: 0, changed_shortlisted: 0, sources_needing_attention: 0 },
            new_high_fit: [],
            changed_shortlisted: [],
            source_health: [],
            since: '2026-10-07T09:00:00Z',
            alert_threshold: 65,
            last_run: null,
          },
        })
      }
      if (path === '/api/v1/trends') {
        return Promise.resolve({
          data: {
            kind: 'skill',
            search_intent_id: 1,
            relevance_min_score: 45,
            available_weeks: 0,
            first_week: null,
            periods: [
              { key: '4w', weeks: 4, available: false },
              { key: '12w', weeks: 12, available: false },
              { key: '6m', weeks: 26, available: false },
            ],
            weeks: [],
            rows: [],
            intent_revision_changes: [],
            source_set_changes: [],
          },
        })
      }
      if (path === '/api/v1/companies') {
        return Promise.resolve({
          data: {
            items: [],
            total: 0,
            window: 15,
            sort: 'new',
            search_intent_id: null,
            relevance_min_score: 45,
          },
        })
      }
      if (path === '/api/v1/inbox') {
        return Promise.resolve({
          data: { items: [], next_cursor: null, counts: { total: 0 }, search_intent_id: null },
        })
      }
      return Promise.resolve({ data: { items: [] }, response: { status: 200 } })
    }),
  },
}))

function renderAt(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ThemeProvider>
        <MemoryRouter initialEntries={[path]}>
          <AppRoutes />
        </MemoryRouter>
      </ThemeProvider>
    </QueryClientProvider>,
  )
}

const ITEMS = [
  'Today',
  'Inbox',
  'Companies',
  'Trends',
  'Sources',
  'Profile & intent',
  'AI & privacy',
]

describe('AppShell', () => {
  it('lists every navigation item', () => {
    renderAt('/inbox')
    const nav = screen.getByRole('navigation', { name: /main/i })
    for (const label of ITEMS) {
      expect(within(nav).getByRole('link', { name: new RegExp(label, 'i') })).toBeInTheDocument()
    }
  })

  it('marks the current page for assistive technology', () => {
    renderAt('/companies')
    const nav = screen.getByRole('navigation', { name: /main/i })
    expect(within(nav).getByRole('link', { name: /companies/i })).toHaveAttribute(
      'aria-current',
      'page',
    )
    expect(within(nav).getByRole('link', { name: /inbox/i })).not.toHaveAttribute('aria-current')
  })

  it('shows the page title in the top bar and navigates on click', async () => {
    renderAt('/inbox')
    expect(screen.getByRole('heading', { level: 1, name: 'Inbox' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('link', { name: /trends/i }))
    expect(screen.getByRole('heading', { level: 1, name: 'Trends' })).toBeInTheDocument()
  })

  it('redirects the root path to the inbox', () => {
    renderAt('/')
    expect(screen.getByRole('heading', { level: 1, name: 'Inbox' })).toBeInTheDocument()
  })

  it('offers a theme switch that changes the document theme', async () => {
    renderAt('/inbox')
    await userEvent.click(screen.getByRole('button', { name: /dark/i }))
    expect(document.documentElement.dataset.theme).toBe('dark')
  })

  it('shows a not-found page for unknown routes', () => {
    renderAt('/nope')
    expect(screen.getByRole('heading', { level: 1, name: /not found/i })).toBeInTheDocument()
  })

  it('credits GeoNames, as its CC BY 4.0 licence requires', () => {
    renderAt('/inbox')
    const link = screen.getByRole('link', { name: 'GeoNames' })
    expect(link).toHaveAttribute('href', 'https://www.geonames.org')
    expect(link).toHaveAttribute('rel', expect.stringContaining('noreferrer'))
    expect(screen.getByText(/CC BY 4\.0/)).toBeInTheDocument()
  })
})
