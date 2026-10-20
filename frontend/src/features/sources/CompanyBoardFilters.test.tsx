import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { CompanyBoardFilters } from './CompanyBoardFilters'
import type { SourceRead } from './queries'

const get = vi.fn()
vi.mock('@/api/client', () => ({ api: { GET: (...a: unknown[]) => get(...a) } }))

const AREAS = [
  { key: 'electrical', label: 'Electrical' },
  { key: 'plumbing_heating', label: 'Plumbing and heating' },
]

const source = (filters: unknown = null) =>
  ({ source_configuration_id: 7, version: 3, filters }) as unknown as SourceRead

function renderFilters(filters: unknown = null) {
  const save = vi.fn()
  const clear = vi.fn()
  const actions = {
    saveFilters: { mutate: save, isPending: false, isError: false },
    clearFilters: { mutate: clear, isPending: false, isError: false },
  } as never
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <CompanyBoardFilters source={source(filters)} actions={actions} />
    </QueryClientProvider>,
  )
  return { save }
}

describe('CompanyBoardFilters', () => {
  beforeEach(() => {
    get.mockReset()
    get.mockResolvedValue({ data: { areas: AREAS } })
  })

  it('offers the areas of work of the owner’s packs, by name', async () => {
    const user = userEvent.setup()
    renderFilters()
    await user.click(screen.getByRole('checkbox', { name: /keep only postings/i }))
    expect(await screen.findByRole('checkbox', { name: 'Electrical' })).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: 'Plumbing and heating' })).toBeInTheDocument()
    expect(screen.getByText('Areas of work')).toBeInTheDocument()
  })

  it('selects every area when the owner opts in, and saves them', async () => {
    const user = userEvent.setup()
    const { save } = renderFilters()
    await screen.findByRole('checkbox', { name: /keep only postings/i })
    await vi.waitFor(() => expect(get).toHaveBeenCalled())
    await user.click(screen.getByRole('checkbox', { name: /keep only postings/i }))
    expect(await screen.findByRole('checkbox', { name: 'Electrical' })).toBeChecked()
    await user.click(screen.getByRole('button', { name: 'Save filters' }))
    expect(save).toHaveBeenCalledWith(
      expect.objectContaining({
        id: 7,
        version: 3,
        filters: expect.objectContaining({ categories: ['electrical', 'plumbing_heating'] }),
      }),
    )
  })

  it('does not insist on an area when no pack offers any', async () => {
    get.mockResolvedValue({ data: { areas: [] } })
    const user = userEvent.setup()
    renderFilters()
    await user.click(screen.getByRole('checkbox', { name: /keep only postings/i }))
    await vi.waitFor(() => expect(get).toHaveBeenCalled())
    expect(screen.queryByText(/choose at least one area/i)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save filters' })).toBeEnabled()
  })
})
