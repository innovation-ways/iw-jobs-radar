import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { NoPackNotice } from './NoPackNotice'

const get = vi.fn()
vi.mock('@/api/client', () => ({ api: { GET: (...a: unknown[]) => get(...a) } }))

function renderNotice() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <NoPackNotice />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('NoPackNotice', () => {
  beforeEach(() => get.mockReset())

  it('points to the Packs screen when no pack is switched on', async () => {
    get.mockResolvedValue({ data: { packs: [], active_count: 0 } })
    renderNotice()
    const notice = await screen.findByRole('status')
    expect(notice).toHaveTextContent(/no pack is switched on/i)
    expect(screen.getByRole('link', { name: /packs/i })).toHaveAttribute('href', '/packs')
  })

  it('stays out of the way when a pack is on', async () => {
    get.mockResolvedValue({ data: { packs: [], active_count: 2 } })
    renderNotice()
    await vi.waitFor(() => expect(get).toHaveBeenCalled())
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('shows nothing when the packs cannot be read', async () => {
    get.mockResolvedValue({ error: { error: { message: 'down' } } })
    renderNotice()
    await vi.waitFor(() => expect(get).toHaveBeenCalled())
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})
