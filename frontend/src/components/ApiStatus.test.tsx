import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiStatus } from './ApiStatus'

const get = vi.fn()
vi.mock('@/api/client', () => ({ api: { GET: (...args: unknown[]) => get(...args) } }))

function renderStatus() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ApiStatus />
    </QueryClientProvider>,
  )
}

describe('ApiStatus', () => {
  beforeEach(() => {
    get.mockReset()
  })

  it('shows ready when database and worker are up', async () => {
    get.mockResolvedValue({
      data: { status: 'ready', components: { database: 'up', worker: 'up' } },
      response: { status: 200 },
    })
    renderStatus()
    expect(await screen.findByText(/API ready/i)).toBeInTheDocument()
    expect(screen.getByText(/worker up/i)).toBeInTheDocument()
  })

  it('names the failing component from a 503 body', async () => {
    get.mockResolvedValue({
      error: { status: 'unavailable', components: { database: 'up', worker: 'stale' } },
      response: { status: 503 },
    })
    renderStatus()
    expect(await screen.findByText(/worker stale/i)).toBeInTheDocument()
    expect(screen.getByText(/needs attention/i)).toBeInTheDocument()
  })

  it('says it is checking before the first answer instead of claiming the API is down', () => {
    get.mockReturnValue(new Promise(() => {})) // never resolves
    renderStatus()
    expect(screen.getByText(/checking api/i)).toBeInTheDocument()
    expect(screen.queryByText(/unreachable/i)).not.toBeInTheDocument()
  })

  it('reports an unreachable API in words, not only colour', async () => {
    get.mockRejectedValue(new Error('network'))
    renderStatus()
    expect(await screen.findByText(/API unreachable/i)).toBeInTheDocument()
  })
})
