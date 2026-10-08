import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Sidebar } from './Sidebar'

const get = vi.fn()
vi.mock('@/api/client', () => ({ api: { GET: (...args: unknown[]) => get(...args) } }))

function renderSidebar() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('navigation badges', () => {
  beforeEach(() => {
    get.mockReset()
    get.mockImplementation((path: string) => {
      if (path === '/api/v1/digests/daily')
        return Promise.resolve({
          data: {
            counts: { new_high_fit: 3, changed_shortlisted: 1, sources_needing_attention: 2 },
          },
        })
      if (path === '/api/v1/inbox')
        return Promise.resolve({ data: { items: [], counts: { unread: 12, updated_unread: 2 } } })
      return Promise.resolve({ data: { status: 'ready', components: {} } })
    })
  })

  it('counts what needs the owner and says so in words', async () => {
    renderSidebar()
    expect(await screen.findByLabelText('4 new on Today')).toHaveTextContent('4')
    expect(screen.getByLabelText('14 to review in Inbox')).toHaveTextContent('14')
    expect(screen.getByLabelText('2 sources need attention')).toHaveTextContent('2')
  })

  it('shows no badge when there is nothing to do', async () => {
    get.mockImplementation((path: string) =>
      path === '/api/v1/digests/daily'
        ? Promise.resolve({
            data: {
              counts: { new_high_fit: 0, changed_shortlisted: 0, sources_needing_attention: 0 },
            },
          })
        : path === '/api/v1/inbox'
          ? Promise.resolve({ data: { items: [], counts: { unread: 0, updated_unread: 0 } } })
          : Promise.resolve({ data: { status: 'ready', components: {} } }),
    )
    renderSidebar()
    await screen.findByRole('link', { name: /Today/ })
    expect(screen.queryByLabelText(/to review|new on|need attention/)).not.toBeInTheDocument()
  })
})
