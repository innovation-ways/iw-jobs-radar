import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Packs } from './Packs'

const get = vi.fn()
const put = vi.fn()
vi.mock('@/api/client', () => ({
  api: { GET: (...a: unknown[]) => get(...a), PUT: (...a: unknown[]) => put(...a) },
}))

function pack(overrides: Record<string, unknown> = {}) {
  return {
    key: 'software_data_it',
    name: 'Software, data and IT',
    description: 'Software engineering, data, AI, DevOps and security roles.',
    version: 1,
    role_family_count: 25,
    sector_count: 16,
    active: true,
    ...overrides,
  }
}

let packs: ReturnType<typeof pack>[]

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <Packs />
    </QueryClientProvider>,
  )
}

describe('Packs screen', () => {
  beforeEach(() => {
    get.mockReset()
    put.mockReset()
    packs = [
      pack(),
      pack({
        key: 'construction_trades',
        name: 'Construction and skilled trades',
        description: 'Electricians, plumbers and site roles.',
        role_family_count: 16,
        sector_count: 5,
        active: false,
      }),
    ]
    get.mockImplementation(() =>
      Promise.resolve({
        data: { packs, active_count: packs.filter((p) => p.active).length },
      }),
    )
  })

  it('shows each pack with what it holds and, in words, whether it is on', async () => {
    renderPage()
    const software = (
      await screen.findByRole('heading', { name: 'Software, data and IT' })
    ).closest('section')!
    expect(within(software).getByText(/25 role families · 16 sectors/)).toBeInTheDocument()
    expect(within(software).getByText('On')).toBeInTheDocument()
    const trades = screen
      .getByRole('heading', { name: 'Construction and skilled trades' })
      .closest('section')!
    expect(within(trades).getByText('Off')).toBeInTheDocument()
    expect(within(trades).getByText(/electricians, plumbers/i)).toBeInTheDocument()
  })

  it('switches a pack on', async () => {
    const user = userEvent.setup()
    put.mockResolvedValue({ data: pack({ key: 'construction_trades', active: true }) })
    renderPage()
    const trades = (
      await screen.findByRole('heading', { name: 'Construction and skilled trades' })
    ).closest('section')!
    await user.click(within(trades).getByRole('button', { name: 'Switch on' }))
    expect(put).toHaveBeenCalledWith('/api/v1/packs/{pack_key}', {
      params: { path: { pack_key: 'construction_trades' } },
      body: { active: true },
    })
  })

  it('switches a pack off', async () => {
    const user = userEvent.setup()
    put.mockResolvedValue({ data: pack({ active: false }) })
    renderPage()
    const software = (
      await screen.findByRole('heading', { name: 'Software, data and IT' })
    ).closest('section')!
    await user.click(within(software).getByRole('button', { name: 'Switch off' }))
    expect(put).toHaveBeenCalledWith('/api/v1/packs/{pack_key}', {
      params: { path: { pack_key: 'software_data_it' } },
      body: { active: false },
    })
  })

  it('says that switching a pack off keeps saved searches and history', async () => {
    renderPage()
    expect(await screen.findByText(/nothing is deleted/i)).toBeInTheDocument()
    expect(screen.getByText(/start from scratch/i)).toBeInTheDocument()
  })

  it('shows why a change failed', async () => {
    const user = userEvent.setup()
    put.mockResolvedValue({
      error: { error: { code: 'not_found', message: "There is no pack 'x'." } },
    })
    renderPage()
    const trades = (
      await screen.findByRole('heading', { name: 'Construction and skilled trades' })
    ).closest('section')!
    await user.click(within(trades).getByRole('button', { name: 'Switch on' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/there is no pack/i)
  })
})
