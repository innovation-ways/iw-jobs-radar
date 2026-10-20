import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Home } from './Home'

const get = vi.fn()
vi.mock('@/api/client', () => ({ api: { GET: (...a: unknown[]) => get(...a) } }))

function renderHome() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route index element={<Home />} />
          <Route path="/setup" element={<p>setup page</p>} />
          <Route path="/inbox" element={<p>inbox page</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('Home', () => {
  beforeEach(() => {
    get.mockReset()
    window.localStorage.clear()
  })

  it('opens the setup on a new installation', async () => {
    get.mockResolvedValue({ data: { needs_setup: true, has_profile: false, active_pack_count: 0 } })
    renderHome()
    expect(await screen.findByText('setup page')).toBeInTheDocument()
  })

  it('opens the inbox for someone who is already set up', async () => {
    get.mockResolvedValue({ data: { needs_setup: false, has_profile: true, active_pack_count: 1 } })
    renderHome()
    expect(await screen.findByText('inbox page')).toBeInTheDocument()
  })

  it('opens the inbox when the owner chose to skip the setup', async () => {
    window.localStorage.setItem('jobs-radar-setup-skipped', '1')
    get.mockResolvedValue({ data: { needs_setup: true, has_profile: false, active_pack_count: 0 } })
    renderHome()
    expect(await screen.findByText('inbox page')).toBeInTheDocument()
  })

  it('never traps the owner: if the status cannot be read, the inbox opens', async () => {
    get.mockResolvedValue({ error: { error: { message: 'down' } } })
    renderHome()
    expect(await screen.findByText('inbox page')).toBeInTheDocument()
  })
})
