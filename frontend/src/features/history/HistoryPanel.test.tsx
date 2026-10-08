import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { makeIntent, makeProfile } from '@/test/builders'
import { HistoryPanel } from './HistoryPanel'

const get = vi.fn()
const post = vi.fn()
vi.mock('@/api/client', () => ({
  api: { GET: (...args: unknown[]) => get(...args), POST: (...args: unknown[]) => post(...args) },
}))

const profile = makeProfile({}, 2)
const revision1 = makeProfile({}, 1).current_revision!
const revision2 = {
  ...profile.current_revision!,
  facts: { ...profile.current_revision!.facts, headline: 'Principal AI engineer' },
}

const summaries = [
  {
    profile_revision_id: 12,
    revision_number: 2,
    created_at: '2026-10-08T11:00:00Z',
    change_summary: 'New headline',
  },
  {
    profile_revision_id: 11,
    revision_number: 1,
    created_at: '2026-10-08T10:00:00Z',
    change_summary: null,
  },
]

const intent1 = makeIntent({}, undefined, 1)
const intent2 = makeIntent({}, { ...intent1.current_revision!.definition, alert_threshold: 80 }, 2)

function setup() {
  get.mockImplementation(
    (path: string, options?: { params?: { path?: Record<string, number> } }) => {
      if (path === '/api/v1/profiles/{career_profile_id}/revisions')
        return Promise.resolve({ data: { items: summaries } })
      if (path === '/api/v1/profiles/{career_profile_id}/revisions/{profile_revision_id}') {
        const id = options?.params?.path?.profile_revision_id
        return Promise.resolve({ data: id === 12 ? revision2 : revision1 })
      }
      if (path === '/api/v1/intents/{search_intent_id}/revisions')
        return Promise.resolve({
          data: { items: [intent2.current_revision, intent1.current_revision] },
        })
      return Promise.reject(new Error(`unexpected GET ${path}`))
    },
  )
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <HistoryPanel profile={profile} intent={intent2} />
    </QueryClientProvider>,
  )
}

const profileRow = (n: number) =>
  screen.getByRole('row', { name: new RegExp(`^${n}\\b`), description: undefined })

describe('HistoryPanel', () => {
  beforeEach(() => {
    get.mockReset()
    post.mockReset()
  })

  it('lists profile and intent revisions newest first and marks the current one', async () => {
    setup()
    const profileTable = await screen.findByRole('table', { name: /profile revisions/i })
    const rows = within(profileTable).getAllByRole('row').slice(1)
    expect(rows).toHaveLength(2)
    expect(within(rows[0]).getByText('current')).toBeInTheDocument()
    expect(within(rows[0]).getByText('New headline')).toBeInTheDocument()
    expect(within(rows[0]).queryByRole('button', { name: /restore/i })).not.toBeInTheDocument()
    expect(within(rows[1]).getByRole('button', { name: /restore revision 1/i })).toBeInTheDocument()
    const intentTable = await screen.findByRole('table', { name: /intent revisions/i })
    expect(within(intentTable).getAllByRole('row')).toHaveLength(3)
  })

  it('shows what a revision contained', async () => {
    setup()
    const table = await screen.findByRole('table', { name: /profile revisions/i })
    await userEvent.click(within(table).getByRole('button', { name: /view revision 1/i }))
    expect(await screen.findByText(/AI solutions engineer/)).toBeInTheDocument()
  })

  it('compares an older revision with the current one', async () => {
    setup()
    const table = await screen.findByRole('table', { name: /profile revisions/i })
    await userEvent.click(within(table).getByRole('button', { name: /compare revision 1/i }))
    const diff = await screen.findByRole('list', { name: /differences/i })
    expect(within(diff).getByText(/headline/i)).toBeInTheDocument()
    expect(within(diff).getByText(/AI solutions engineer/)).toBeInTheDocument()
    expect(within(diff).getByText(/Principal AI engineer/)).toBeInTheDocument()
  })

  it('compares intent revisions', async () => {
    setup()
    const table = await screen.findByRole('table', { name: /intent revisions/i })
    await userEvent.click(within(table).getByRole('button', { name: /compare revision 1/i }))
    const diff = await screen.findByRole('list', { name: /differences/i })
    expect(within(diff).getByText(/alert_threshold/i)).toBeInTheDocument()
  })

  it('restores an old revision as a new one using the current revision number', async () => {
    post.mockResolvedValue({
      data: { created: true, profile: makeProfile({}, 3) },
      response: { status: 200 },
    })
    setup()
    const table = await screen.findByRole('table', { name: /profile revisions/i })
    await userEvent.click(within(table).getByRole('button', { name: /restore revision 1/i }))
    expect(post).toHaveBeenCalledWith(
      '/api/v1/profiles/{career_profile_id}/revisions/{profile_revision_id}/restore',
      {
        params: { path: { career_profile_id: 1, profile_revision_id: 11 } },
        body: { expected_current_revision: 2 },
      },
    )
    expect(await screen.findByRole('status')).toHaveTextContent(
      /restored revision 1 as revision 3/i,
    )
  })

  it('says when restoring changes nothing', async () => {
    post.mockResolvedValue({
      data: { created: false, profile: profile },
      response: { status: 200 },
    })
    setup()
    const table = await screen.findByRole('table', { name: /profile revisions/i })
    await userEvent.click(within(table).getByRole('button', { name: /restore revision 1/i }))
    expect(await screen.findByRole('status')).toHaveTextContent(/identical to the current/i)
  })

  it('shows why a restore failed', async () => {
    post.mockResolvedValue({
      error: {
        error: {
          code: 'conflict',
          message: 'The profile changed since it was loaded.',
          details: {},
        },
      },
      response: { status: 409 },
    })
    setup()
    const table = await screen.findByRole('table', { name: /profile revisions/i })
    await userEvent.click(within(table).getByRole('button', { name: /restore revision 1/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/changed since it was loaded/i)
  })

  it('explains the append-only rule', async () => {
    setup()
    expect(await screen.findByText(/nothing is overwritten/i)).toBeInTheDocument()
    expect(profileRow).toBeDefined()
  })
})
