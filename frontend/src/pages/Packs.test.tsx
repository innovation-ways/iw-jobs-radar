import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Packs } from './Packs'

const get = vi.fn()
const put = vi.fn()
const post = vi.fn()
vi.mock('@/api/client', () => ({
  api: {
    GET: (...a: unknown[]) => get(...a),
    PUT: (...a: unknown[]) => put(...a),
    POST: (...a: unknown[]) => post(...a),
  },
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
let preview: Record<string, unknown>

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
    post.mockReset()
    preview = { candidates: 120, model: 'qwen3:8b', seconds_per_job: 12, minutes: 24 }
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
    get.mockImplementation((path: string) =>
      Promise.resolve({
        data:
          path === '/api/v1/pipeline/re-extraction'
            ? preview
            : { packs, active_count: packs.filter((p) => p.active).length },
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

  describe('analysing open jobs again', () => {
    async function card() {
      renderPage()
      return (await screen.findByRole('heading', { name: 'Analyse open jobs again' })).closest(
        'section',
      )!
    }

    it('says how many jobs and how long, and changes nothing until confirmed', async () => {
      const section = await card()
      expect(await within(section).findByText(/120 open jobs/i)).toBeInTheDocument()
      expect(within(section).getByText(/about 24 minutes/i)).toBeInTheDocument()
      expect(within(section).getByText(/qwen3:8b/)).toBeInTheDocument()
      expect(post).not.toHaveBeenCalled()
    })

    it('queues the analyses after the owner confirms, for the chosen window', async () => {
      const user = userEvent.setup()
      post.mockResolvedValue({ data: { queued: 120 } })
      const section = await card()
      await user.selectOptions(within(section).getByLabelText('First seen in the last'), '90')
      await user.click(
        await within(section).findByRole('button', { name: /analyse 120 jobs again/i }),
      )
      expect(post).toHaveBeenCalledWith('/api/v1/pipeline/re-extraction', {
        body: { since_days: 90 },
      })
      expect(await within(section).findByText(/120 jobs queued/i)).toBeInTheDocument()
    })

    it('has nothing to offer when no job needs it', async () => {
      preview = { candidates: 0, model: 'qwen3:8b', seconds_per_job: 12, minutes: 0 }
      const section = await card()
      expect(await within(section).findByText(/no open job needs it/i)).toBeInTheDocument()
      expect(within(section).queryByRole('button', { name: /analyse/i })).not.toBeInTheDocument()
    })

    it('explains why it cannot count when no model is chosen', async () => {
      get.mockImplementation((path: string) =>
        path === '/api/v1/pipeline/re-extraction'
          ? Promise.resolve({
              error: {
                error: {
                  code: 'conflict',
                  message: 'Choose the model that analyses jobs in AI & privacy first.',
                },
              },
            })
          : Promise.resolve({ data: { packs, active_count: 1 } }),
      )
      const section = await card()
      expect(
        await within(section).findByText(/choose the model that analyses jobs/i),
      ).toBeInTheDocument()
    })
  })
})
