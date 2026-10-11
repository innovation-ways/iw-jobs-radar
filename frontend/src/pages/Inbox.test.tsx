import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { makeIntent, makeProfile } from '@/test/builders'
import {
  makeCounts,
  makeDetail,
  makeDimension,
  makeItem,
  makeUnscored,
  type Item,
} from '@/test/inboxBuilders'
import { Inbox } from './Inbox'

const get = vi.fn()
const post = vi.fn()
vi.mock('@/api/client', () => ({
  api: { GET: (...args: unknown[]) => get(...args), POST: (...args: unknown[]) => post(...args) },
}))

let items: Item[]
let counts = makeCounts()
let nextCursor: string | null = null

function listQuery(call: unknown[]) {
  return (call[1] as { params: { query: Record<string, unknown> } }).params.query
}
const lastListQuery = () =>
  listQuery(get.mock.calls.filter(([path]) => path === '/api/v1/inbox').at(-1)!)

function renderInbox(url = '/') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[url]}>
        <Inbox />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function install(overrides: { intents?: boolean } = {}) {
  get.mockImplementation(
    (path: string, options?: { params?: { path?: Record<string, number> } }) => {
      switch (path) {
        case '/api/v1/profiles':
          return Promise.resolve({ data: { items: [makeProfile()] } })
        case '/api/v1/profiles/{career_profile_id}/intents':
          return Promise.resolve({
            data: {
              items:
                overrides.intents === false
                  ? []
                  : [makeIntent({ search_intent_id: 5, title: 'Remote first' })],
            },
          })
        case '/api/v1/inbox':
          return Promise.resolve({
            data: { items, next_cursor: nextCursor, counts, search_intent_id: 5 },
          })
        case '/api/v1/inbox/{job_inbox_item_id}': {
          const id = options?.params?.path?.job_inbox_item_id
          const item = items.find((i) => i.job_inbox_item_id === id)!
          return Promise.resolve({ data: makeDetail(item) })
        }
        default:
          return Promise.reject(new Error(`unexpected GET ${path}`))
      }
    },
  )
}

const row = (title: RegExp | string) => screen.getByRole('option', { name: title })

describe('Inbox screen', () => {
  beforeEach(() => {
    get.mockReset()
    post.mockReset()
    localStorage.clear()
    items = [
      makeItem({ job_inbox_item_id: 1, title: 'Applied AI Architect' }),
      makeItem({
        job_inbox_item_id: 2,
        title: 'Platform Engineer',
        evaluation: { ...makeItem().evaluation!, fit_score: 61, fit_band: 'average' },
      }),
      makeUnscored({ job_inbox_item_id: 3, title: 'Data Analyst' }),
    ]
    counts = makeCounts()
    nextCursor = null
    install()
  })

  afterEach(() => vi.useRealTimers())

  describe('list', () => {
    it('shows the tabs with counts and the jobs in the order the API gave', async () => {
      renderInbox()
      await screen.findByRole('option', { name: /Applied AI Architect/ }) // the sort/filter selects also have options
      const tabs = screen.getByRole('tablist', { name: /inbox sections/i })
      expect(
        within(tabs)
          .getAllByRole('tab')
          .map((t) => t.textContent),
      ).toEqual([
        'To review4',
        'Updated1',
        'Set aside6',
        'Shortlist2',
        'Reviewed2',
        'Ignored3',
        'Archived0',
        'Applied1',
      ])
      expect(within(tabs).getByRole('tab', { name: /to review/i })).toHaveAttribute(
        'aria-selected',
        'true',
      )
      const options = within(await screen.findByRole('listbox')).getAllByRole('option')
      expect(options.map((o) => o.textContent)).toEqual([
        expect.stringContaining('Applied AI Architect'),
        expect.stringContaining('Platform Engineer'),
        expect.stringContaining('Data Analyst'),
      ])
    })

    it('shows the score, its band in words, and signals with icons and words for status', async () => {
      renderInbox()
      const first = await screen.findByRole('option', { name: /Applied AI Architect/ })
      expect(within(first).getByText('82')).toBeInTheDocument()
      expect(within(first).getByText('Excellent')).toBeInTheDocument()
      expect(within(first).getByText('Northwind Labs')).toBeInTheDocument()
      expect(within(first).getByText('Remote - EU')).toBeInTheDocument()
      expect(within(first).getByText('NEW')).toBeInTheDocument()
      for (const label of ['Work', 'Engagement', 'Pay', 'Skills']) {
        expect(within(first).getByText(label, { exact: false })).toBeInTheDocument()
      }
      expect(within(first).getByText('(unknown)')).toBeInTheDocument() // screen-reader status for Pay
    })

    it('lists jobs without a score as not evaluated', async () => {
      renderInbox()
      const unscored = await screen.findByRole('option', { name: /Data Analyst/ })
      expect(within(unscored).getByText('Pending')).toBeInTheDocument()
      expect(within(unscored).queryByText('NEW')).toBeInTheDocument()
    })

    it('marks shortlisted, updated and multi-site jobs', async () => {
      items = [
        makeItem({
          job_inbox_item_id: 1,
          is_shortlisted: true,
          state: 'updated_unread',
          title: 'Starred',
        }),
        makeItem({
          job_inbox_item_id: 2,
          title: 'Two sites',
          sources: [
            makeItem().sources[0],
            {
              ...makeItem().sources[0],
              job_posting_id: 999,
              job_opportunity_link_id: 998,
              source_name: 'JobPortal',
            },
          ],
        }),
      ]
      renderInbox()
      const starred = await screen.findByRole('option', { name: /Starred/ })
      expect(within(starred).getByLabelText('Shortlisted')).toBeInTheDocument()
      expect(within(starred).getByText('UPDATED')).toBeInTheDocument()
      expect(within(row(/Two sites/)).getByText('2 sites')).toBeInTheDocument()
    })

    it('says when there is nothing in a tab', async () => {
      items = []
      renderInbox()
      expect(await screen.findByText(/nothing here/i)).toBeInTheDocument()
    })

    it('guides the owner to collect jobs when the inbox is completely empty', async () => {
      items = []
      counts = makeCounts({
        unread: 0,
        read: 0,
        updated_unread: 0,
        ignored: 0,
        archived: 0,
        applied: 0,
        shortlisted: 0,
        total: 0,
      })
      renderInbox()
      expect(await screen.findByText(/no jobs yet/i)).toBeInTheDocument()
      expect(screen.getByRole('link', { name: /sources/i })).toHaveAttribute('href', '/sources')
    })

    it('loads more jobs with the cursor', async () => {
      nextCursor = 'CURSOR1'
      renderInbox()
      await screen.findByRole('option', { name: /Applied AI Architect/ })
      nextCursor = null
      await userEvent.click(screen.getByRole('button', { name: /show more/i }))
      await waitFor(() => expect(lastListQuery().cursor).toBe('CURSOR1'))
    })

    it('reports a load failure and lets the owner retry', async () => {
      const original = get.getMockImplementation()!
      let failed = false
      get.mockImplementation((path: string, options?: unknown) => {
        if (path === '/api/v1/inbox' && !failed) {
          failed = true
          return Promise.reject(new Error('network'))
        }
        return original(path, options as never)
      })
      renderInbox()
      expect(await screen.findByRole('alert')).toHaveTextContent(/could not load/i)
      await userEvent.click(screen.getByRole('button', { name: /try again/i }))
      expect(
        await screen.findByRole('option', { name: /Applied AI Architect/ }),
      ).toBeInTheDocument()
    })
  })

  describe('sections and search', () => {
    it('asks for the right state per tab', async () => {
      renderInbox()
      await screen.findByRole('option', { name: /Applied AI Architect/ })
      expect(lastListQuery()).toMatchObject({
        state: 'unread',
        search_intent_id: 5,
        sort: 'fit_desc',
      })

      // ADR-058: jobs the owner cannot apply for are not in "To review".
      expect(lastListQuery().set_aside).toBe(false)

      await userEvent.click(screen.getByRole('tab', { name: /set aside/i }))
      await waitFor(() =>
        expect(lastListQuery()).toMatchObject({ state: 'unread', set_aside: true }),
      )

      await userEvent.click(screen.getByRole('tab', { name: /updated/i }))
      await waitFor(() => expect(lastListQuery().state).toBe('updated_unread'))

      await userEvent.click(screen.getByRole('tab', { name: /shortlist/i }))
      await waitFor(() =>
        expect(lastListQuery()).toMatchObject({ state: 'all', shortlisted: true }),
      )

      await userEvent.click(screen.getByRole('tab', { name: /reviewed/i }))
      await waitFor(() => expect(lastListQuery().state).toBe('read'))
      await userEvent.click(screen.getByRole('tab', { name: /ignored/i }))
      await waitFor(() => expect(lastListQuery().state).toBe('ignored'))
    })

    it('searches after the owner stops typing', async () => {
      renderInbox()
      await screen.findByRole('option', { name: /Applied AI Architect/ })
      await userEvent.type(screen.getByRole('searchbox', { name: /search jobs/i }), 'kuber')
      await waitFor(() => expect(lastListQuery().q).toBe('kuber'))
    })

    it('sorts by best fit by default and lets the owner change the order, remembering it', async () => {
      renderInbox()
      await screen.findByRole('option', { name: /Applied AI Architect/ })
      expect(lastListQuery().sort).toBe('fit_desc')
      await userEvent.selectOptions(screen.getByLabelText('Sort by'), 'newest')
      await waitFor(() => expect(lastListQuery().sort).toBe('newest'))
      expect(localStorage.getItem('jobs-radar:inbox-sort')).toBe('newest')
    })

    it('starts from the remembered sort order', async () => {
      localStorage.setItem('jobs-radar:inbox-sort', 'oldest')
      renderInbox()
      await screen.findByRole('option', { name: /Applied AI Architect/ })
      expect(lastListQuery().sort).toBe('oldest')
      expect(screen.getByLabelText('Sort by')).toHaveValue('oldest')
    })

    it('opens already filtered to the jobs not evaluated when the link says so', async () => {
      renderInbox('/inbox?fit=unscored')
      await screen.findByRole('option', { name: /Applied AI Architect/ })
      expect(lastListQuery()).toMatchObject({ evaluated: false })
      expect(screen.getByLabelText('Fit')).toHaveValue('unscored')
    })

    it('ignores an unknown fit in the link', async () => {
      renderInbox('/inbox?fit=bogus')
      await screen.findByRole('option', { name: /Applied AI Architect/ })
      expect(screen.getByLabelText('Fit')).toHaveValue('any')
    })

    it('filters by fit and by when the job was first seen, and clears the filters', async () => {
      renderInbox()
      await screen.findByRole('option', { name: /Applied AI Architect/ })
      expect(screen.queryByRole('button', { name: 'Clear filters' })).not.toBeInTheDocument()

      await userEvent.selectOptions(screen.getByLabelText('Fit'), '65')
      await waitFor(() => expect(lastListQuery().fit_min).toBe(65))
      await userEvent.selectOptions(screen.getByLabelText('First seen'), '7d')
      await waitFor(() => expect(typeof lastListQuery().from).toBe('string'))

      await userEvent.selectOptions(screen.getByLabelText('Fit'), 'unscored')
      await waitFor(() => expect(lastListQuery()).toMatchObject({ evaluated: false }))
      expect(lastListQuery().fit_min).toBeUndefined()

      await userEvent.click(screen.getByRole('button', { name: 'Clear filters' }))
      await waitFor(() => expect(lastListQuery().from).toBeUndefined())
      expect(lastListQuery().evaluated).toBeUndefined()
      expect(screen.getByLabelText('Fit')).toHaveValue('any')
    })
  })

  describe('detail', () => {
    it('shows the first job in the detail panel with its score and band', async () => {
      renderInbox()
      const detail = await screen.findByRole('article', { name: /Applied AI Architect/ })
      expect(within(detail).getByRole('meter', { name: /fit score/i })).toHaveAttribute(
        'aria-valuenow',
        '82',
      )
      expect(within(detail).getByText('Excellent fit')).toBeInTheDocument()
      expect(within(detail).getByText(/Northwind Labs/)).toBeInTheDocument()
    })

    it('shows a different job after selecting it, and with the keyboard (j and k)', async () => {
      renderInbox()
      await screen.findByRole('article', { name: /Applied AI Architect/ })
      await userEvent.click(row(/Platform Engineer/))
      expect(await screen.findByRole('article', { name: /Platform Engineer/ })).toBeInTheDocument()
      await userEvent.keyboard('j')
      expect(await screen.findByRole('article', { name: /Data Analyst/ })).toBeInTheDocument()
      await userEvent.keyboard('k')
      expect(await screen.findByRole('article', { name: /Platform Engineer/ })).toBeInTheDocument()
    })

    it('explains each dimension and shows the posting words on hover or focus', async () => {
      renderInbox()
      const detail = await screen.findByRole('article', { name: /Applied AI Architect/ })
      const dimension = within(detail).getByRole('listitem', {
        name: /Work arrangement & location/i,
      })
      expect(within(dimension).getByText('Match')).toBeInTheDocument()
      const tooltip = within(dimension).getByRole('tooltip')
      expect(tooltip).toHaveTextContent('Fully remote within EU time zones.')
      expect(tooltip).toHaveTextContent('Remote work is open from your region.')
      const unknown = within(detail).getByRole('listitem', { name: /Compensation/i })
      expect(within(unknown).getByText(/unknown/i)).toBeInTheDocument()
      expect(within(unknown).getByRole('tooltip')).toHaveTextContent(/does not state pay/i)
    })

    it('explains a job that has no score and still lets the owner decide', async () => {
      renderInbox()
      await screen.findByRole('article', { name: /Applied AI Architect/ })
      await userEvent.click(row(/Data Analyst/))
      const detail = await screen.findByRole('article', { name: /Data Analyst/ })
      expect(within(detail).getByText('Not evaluated')).toBeInTheDocument()
      expect(within(detail).getByText(/has not been scored yet/i)).toBeInTheDocument()
      expect(within(detail).getByRole('button', { name: /ignore/i })).toBeEnabled()
    })

    it('shows the hard constraints that made a job not recommended', async () => {
      items = [
        makeItem({
          job_inbox_item_id: 1,
          title: 'Gated',
          evaluation: {
            ...makeItem().evaluation!,
            fit_band: 'not_recommended',
            recommendation: 'not_recommended',
            gates: [
              {
                code: 'G2',
                reason: 'Remote work is not open from any of your regions.',
                evidence: {},
              },
            ],
          },
        }),
      ]
      renderInbox()
      const detail = await screen.findByRole('article', { name: /Gated/ })
      expect(within(detail).getByText('Not recommended')).toBeInTheDocument()
      expect(within(detail).getByText(/not open from any of your regions/i)).toBeInTheDocument()
    })

    it('shows what changed when a job was updated', async () => {
      get.mockImplementation(
        (path: string, options?: { params?: { path?: Record<string, number> } }) => {
          if (path === '/api/v1/inbox/{job_inbox_item_id}')
            return Promise.resolve({
              data: makeDetail(items[0], {
                last_change: {
                  changed_fields: ['title', 'description'],
                  created_at: '2026-10-09T08:00:00Z',
                },
              }),
            })
          return install_default(path, options)
        },
      )
      renderInbox()
      expect(
        await screen.findByText(
          (_, el) =>
            el?.tagName === 'P' && /updated: title, description/i.test(el.textContent ?? ''),
        ),
      ).toBeInTheDocument()
    })

    it('lists where the job was seen and flags a possible duplicate with a decision', async () => {
      const possible = {
        ...makeItem().sources[0],
        job_posting_id: 777,
        job_opportunity_link_id: 555,
        source_name: 'JobPortal',
        link_state: 'possible' as const,
        similarity: 0.8,
      }
      items = [
        makeItem({
          job_inbox_item_id: 1,
          title: 'Dup',
          sources: [makeItem().sources[0], possible],
          possible_duplicate: true,
        }),
      ]
      post.mockResolvedValue({
        data: { job_opportunity_id: 101, state: 'confirmed' },
        response: { status: 200 },
      })
      renderInbox()
      const detail = await screen.findByRole('article', { name: /Dup/ })
      expect(within(detail).getAllByText(/JobPortal/).length).toBeGreaterThan(0)
      expect(within(detail).getByText(/may be the same job/i)).toBeInTheDocument()
      await userEvent.click(within(detail).getByRole('button', { name: /same job/i }))
      expect(post).toHaveBeenCalledWith(
        '/api/v1/opportunity-links/{job_opportunity_link_id}/confirm',
        {
          params: { path: { job_opportunity_link_id: 555 } },
        },
      )
      await userEvent.click(within(detail).getByRole('button', { name: /different job/i }))
      expect(post).toHaveBeenCalledWith(
        '/api/v1/opportunity-links/{job_opportunity_link_id}/reject',
        {
          params: { path: { job_opportunity_link_id: 555 } },
        },
      )
    })
  })

  describe('actions', () => {
    const acted = (item: Item, patch: Partial<Item>) => ({
      data: {
        item: { ...item, ...patch, version: item.version + 1 },
        event: {
          inbox_event_id: 1,
          action: 'x',
          actor: 'user',
          from_state: null,
          to_state: 'x',
          created_at: '2026-10-08T12:00:00Z',
        },
      },
      response: { status: 200 },
    })

    it('shortlists with the version the owner saw and offers to undo it', async () => {
      post.mockResolvedValue(acted(items[0], { is_shortlisted: true }))
      renderInbox()
      const detail = await screen.findByRole('article', { name: /Applied AI Architect/ })
      await userEvent.click(within(detail).getByRole('button', { name: /^☆ Shortlist/ }))
      expect(post).toHaveBeenCalledWith('/api/v1/inbox/{job_inbox_item_id}/actions', {
        params: { path: { job_inbox_item_id: 1 }, query: { search_intent_id: 5 } },
        body: { action: 'shortlist', expected_version: 1 },
      })
      const toast = await screen.findByRole('status')
      expect(toast).toHaveTextContent(/added to shortlist/i)
      post.mockResolvedValue(acted({ ...items[0], version: 2 }, { is_shortlisted: false }))
      await userEvent.click(within(toast).getByRole('button', { name: /undo/i }))
      await waitFor(() =>
        expect(post).toHaveBeenLastCalledWith(
          '/api/v1/inbox/{job_inbox_item_id}/actions',
          expect.objectContaining({ body: { action: 'unshortlist', expected_version: 2 } }),
        ),
      )
    })

    it('ignores a job and undoing returns it to unread through restore then mark unread', async () => {
      post.mockResolvedValueOnce(acted(items[0], { state: 'ignored' }))
      renderInbox()
      const detail = await screen.findByRole('article', { name: /Applied AI Architect/ })
      await userEvent.click(within(detail).getByRole('button', { name: /^ignore/i }))
      const toast = await screen.findByRole('status')
      expect(toast).toHaveTextContent(/ignored/i)
      post
        .mockResolvedValueOnce(acted({ ...items[0], version: 2 }, { state: 'read' }))
        .mockResolvedValueOnce(acted({ ...items[0], version: 3 }, { state: 'unread' }))
      await userEvent.click(within(toast).getByRole('button', { name: /undo/i }))
      await waitFor(() => expect(post).toHaveBeenCalledTimes(3))
      expect(post.mock.calls[1][1].body).toEqual({ action: 'restore', expected_version: 2 })
      expect(post.mock.calls[2][1].body).toEqual({ action: 'mark_unread', expected_version: 3 })
    })

    it('uses keyboard shortcuts for the actions and for undo', async () => {
      post.mockResolvedValue(acted(items[0], { state: 'archived' }))
      renderInbox()
      await screen.findByRole('article', { name: /Applied AI Architect/ })
      await userEvent.keyboard('e')
      await waitFor(() => expect(post.mock.calls[0][1].body.action).toBe('archive'))
      post.mockResolvedValue(acted({ ...items[0], version: 2 }, { state: 'unread' }))
      await userEvent.keyboard('z')
      await waitFor(() => expect(post.mock.calls.at(-1)![1].body.action).toBe('mark_unread'))
    })

    it('records an application', async () => {
      post.mockResolvedValue(acted(items[0], { state: 'applied' }))
      renderInbox()
      const detail = await screen.findByRole('article', { name: /Applied AI Architect/ })
      await userEvent.click(within(detail).getByRole('button', { name: /mark applied/i }))
      expect(post.mock.calls[0][1].body).toEqual({
        action: 'record_application',
        expected_version: 1,
      })
    })

    it('offers restore for ignored jobs instead of ignore', async () => {
      items = [makeItem({ job_inbox_item_id: 1, title: 'Skipped', state: 'ignored' })]
      renderInbox()
      const detail = await screen.findByRole('article', { name: /Skipped/ })
      expect(within(detail).getByRole('button', { name: /restore/i })).toBeInTheDocument()
      expect(within(detail).queryByRole('button', { name: /^ignore/i })).not.toBeInTheDocument()
      expect(
        within(detail).getByText(
          (_, el) => el?.tagName === 'P' && /this job is ignored/i.test(el.textContent ?? ''),
        ),
      ).toBeInTheDocument()
    })

    it('opens the original without changing the job, so it stays in the list', async () => {
      renderInbox()
      const detail = await screen.findByRole('article', { name: /Applied AI Architect/ })
      const link = within(detail).getByRole('link', { name: /open original/i })
      expect(link).toHaveAttribute('href', 'https://careers.example.test/apply/1')
      expect(link).toHaveAttribute('target', '_blank')
      expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'))
      link.addEventListener('click', (event) => event.preventDefault()) // do not navigate in jsdom
      await userEvent.click(link)
      // Only an explicit button (ignore, archive, applied...) may take a job out of "To review".
      expect(post).not.toHaveBeenCalled()
    })

    it('tells the owner when the job changed elsewhere (409) and refreshes', async () => {
      post.mockResolvedValue({
        error: {
          error: {
            code: 'conflict',
            message: 'The inbox item changed since it was loaded.',
            details: {},
          },
        },
        response: { status: 409 },
      })
      renderInbox()
      const detail = await screen.findByRole('article', { name: /Applied AI Architect/ })
      await userEvent.click(within(detail).getByRole('button', { name: /^ignore/i }))
      expect(await screen.findByRole('alert')).toHaveTextContent(/changed since it was loaded/i)
    })
  })

  describe('density and help', () => {
    it('switches between comfortable and compact and remembers the choice', async () => {
      renderInbox()
      const first = await screen.findByRole('option', { name: /Applied AI Architect/ })
      expect(within(first).getByText('Pay', { exact: false })).toBeInTheDocument()
      await userEvent.click(screen.getByRole('button', { name: 'Compact' }))
      expect(screen.getByRole('button', { name: 'Compact' })).toHaveAttribute(
        'aria-pressed',
        'true',
      )
      expect(screen.getByTestId('inbox-root')).toHaveAttribute('data-density', 'compact')
      expect(localStorage.getItem('jobs-radar:inbox-density')).toBe('compact')
    })

    it('shows the keyboard shortcuts and closes them with Escape', async () => {
      renderInbox()
      await screen.findByRole('option', { name: /Applied AI Architect/ })
      await userEvent.keyboard('?')
      const help = await screen.findByRole('dialog', { name: /keyboard shortcuts/i })
      expect(within(help).getByText(/shortlist/i)).toBeInTheDocument()
      await userEvent.keyboard('{Escape}')
      await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    })
  })

  describe('without a search intent', () => {
    it('lists jobs as not evaluated and points to Profile & intent', async () => {
      install({ intents: false })
      items = [makeUnscored({ job_inbox_item_id: 1, title: 'Waiting job' })]
      renderInbox()
      expect(await screen.findByText(/create a search intent/i)).toBeInTheDocument()
      expect(screen.getByRole('link', { name: /profile & intent/i })).toHaveAttribute(
        'href',
        '/profile',
      )
      expect(await screen.findByRole('option', { name: /Waiting job/ })).toBeInTheDocument()
      expect(lastListQuery().search_intent_id).toBeUndefined()
    })
  })

  it('has no accessibility-breaking duplicates: one meter per detail', async () => {
    renderInbox()
    const detail = await screen.findByRole('article', { name: /Applied AI Architect/ })
    expect(within(detail).getAllByRole('meter')).toHaveLength(1)
    expect(makeDimension().dimension_key).toBe('work_arrangement_location')
  })
})

function install_default(path: string, options?: { params?: { path?: Record<string, number> } }) {
  // used by tests that override only the detail endpoint
  const original = get.getMockImplementation()
  void original
  switch (path) {
    case '/api/v1/profiles':
      return Promise.resolve({ data: { items: [makeProfile()] } })
    case '/api/v1/profiles/{career_profile_id}/intents':
      return Promise.resolve({
        data: { items: [makeIntent({ search_intent_id: 5, title: 'Remote first' })] },
      })
    case '/api/v1/inbox':
      return Promise.resolve({
        data: { items, next_cursor: nextCursor, counts, search_intent_id: 5 },
      })
    default:
      void options
      return Promise.reject(new Error(`unexpected GET ${path}`))
  }
}
