import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Vocabulary } from './Vocabulary'

const get = vi.fn()
const post = vi.fn()
const patch = vi.fn()
vi.mock('@/api/client', () => ({
  api: {
    GET: (...a: unknown[]) => get(...a),
    POST: (...a: unknown[]) => post(...a),
    PATCH: (...a: unknown[]) => patch(...a),
  },
}))

function term(overrides: Record<string, unknown> = {}) {
  return {
    kind: 'role_family',
    term_key: 'security',
    label: 'Security',
    origin: 'seed',
    active: true,
    introduced_in_taxonomy_version_id: 1,
    ...overrides,
  }
}

let terms: Record<string, unknown>[]

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <Vocabulary />
    </QueryClientProvider>,
  )
}

describe('Vocabulary screen', () => {
  beforeEach(() => {
    for (const m of [get, post, patch]) m.mockReset()
    terms = [
      term(),
      term({ term_key: 'electrician', label: 'Electrician', origin: 'user' }),
      term({ term_key: 'plumbing', label: 'Plumbing', origin: 'user', active: false }),
      term({ kind: 'sector', term_key: 'telecom', label: 'Telecom' }),
    ]
    get.mockImplementation(() => Promise.resolve({ data: { taxonomy_version_id: 3, terms } }))
  })

  it('lists role families and sectors with where each term came from', async () => {
    renderPage()
    const families = (await screen.findByRole('heading', { name: 'Role families' })).closest(
      'section',
    )!
    expect(within(families).getByText('Security')).toBeInTheDocument()
    expect(within(families).getByText('Electrician')).toBeInTheDocument()
    expect(within(families).getAllByText('Added by you')).toHaveLength(2)
    expect(within(families).getAllByText('Built in')).toHaveLength(1)
    const sectors = screen.getByRole('heading', { name: 'Sectors' }).closest('section')!
    expect(within(sectors).getByText('Telecom')).toBeInTheDocument()
  })

  it('says in words, not only by colour, which terms are switched off', async () => {
    renderPage()
    const row = (await screen.findByText('Plumbing')).closest('li')!
    expect(within(row).getByText('Switched off')).toBeInTheDocument()
    expect(within(row).getByRole('checkbox', { name: /offer plumbing/i })).not.toBeChecked()
  })

  it('adds a term to the chosen vocabulary', async () => {
    const user = userEvent.setup()
    post.mockResolvedValue({
      data: term({ term_key: 'welding', label: 'Welding', origin: 'user' }),
    })
    renderPage()
    const families = (await screen.findByRole('heading', { name: 'Role families' })).closest(
      'section',
    )!
    await user.type(within(families).getByLabelText('New role family'), 'Welding')
    await user.click(within(families).getByRole('button', { name: 'Add' }))
    expect(post).toHaveBeenCalledWith('/api/v1/taxonomy/terms', {
      body: { kind: 'role_family', label: 'Welding' },
    })
  })

  it('shows the reason when a term cannot be added', async () => {
    const user = userEvent.setup()
    post.mockResolvedValue({
      error: {
        error: { code: 'conflict', message: "There is already a sector called 'Telecom'." },
      },
    })
    renderPage()
    const sectors = (await screen.findByRole('heading', { name: 'Sectors' })).closest('section')!
    await user.type(within(sectors).getByLabelText('New sector'), 'telecom')
    await user.click(within(sectors).getByRole('button', { name: 'Add' }))
    expect(await within(sectors).findByRole('alert')).toHaveTextContent(/already a sector/i)
  })

  it('switches a term off and on', async () => {
    const user = userEvent.setup()
    patch.mockResolvedValue({ data: term({ active: false }) })
    renderPage()
    await user.click(await screen.findByRole('checkbox', { name: /offer security/i }))
    expect(patch).toHaveBeenCalledWith('/api/v1/taxonomy/terms/{kind}/{term_key}', {
      params: { path: { kind: 'role_family', term_key: 'security' } },
      body: { active: false },
    })
  })

  it('renames a term without touching its key', async () => {
    const user = userEvent.setup()
    patch.mockResolvedValue({ data: term({ label: 'Information security' }) })
    renderPage()
    const row = (await screen.findByText('Security')).closest('li')!
    await user.click(within(row).getByRole('button', { name: /rename security/i }))
    const field = within(row).getByLabelText('Label of Security')
    await user.clear(field)
    await user.type(field, 'Information security')
    await user.click(within(row).getByRole('button', { name: 'Save' }))
    expect(patch).toHaveBeenCalledWith('/api/v1/taxonomy/terms/{kind}/{term_key}', {
      params: { path: { kind: 'role_family', term_key: 'security' } },
      body: { label: 'Information security' },
    })
  })

  it('explains what switching off does', async () => {
    renderPage()
    expect(await screen.findByText(/stay in saved searches and history/i)).toBeInTheDocument()
  })
})
