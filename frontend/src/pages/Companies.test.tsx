import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Companies } from './Companies'

const get = vi.fn()
const post = vi.fn()
const put = vi.fn()
const del = vi.fn()
vi.mock('@/api/client', () => ({
  api: {
    GET: (...a: unknown[]) => get(...a),
    POST: (...a: unknown[]) => post(...a),
    PUT: (...a: unknown[]) => put(...a),
    DELETE: (...a: unknown[]) => del(...a),
  },
}))

function company(id: number, name: string, overrides: Record<string, unknown> = {}) {
  return {
    company_id: id,
    name,
    homepage_url: null,
    careers_url: null,
    employer_type: null,
    open_offers: 5,
    recommended_offers: 2,
    best_fit_score: 82,
    pending_candidates: 0,
    is_followed: false,
    is_ignored: false,
    ...overrides,
  }
}

function dossier(overrides: Record<string, unknown> = {}) {
  return {
    company_id: 1,
    name: 'Northwind Labs',
    homepage_url: 'https://www.northwind.example/',
    careers_url: null,
    employer_type: null,
    enriched_at: '2026-10-08T09:00:00Z',
    stale: false,
    is_followed: false,
    is_ignored: false,
    offers_truncated: false,
    facts: [
      {
        fact_key: 'industry',
        value: 'software industry',
        origin: 'public_dataset',
        label: 'Source',
        source_name: 'wikidata',
        source_url: 'https://www.wikidata.org/wiki/Q1',
        retrieved_at: '2026-10-08T09:00:00Z',
        licence: 'CC0-1.0',
        confidence: null,
      },
      {
        fact_key: 'description',
        value: 'Northwind Labs is a software company.',
        origin: 'public_dataset',
        label: 'Source',
        source_name: 'wikipedia',
        source_url: 'https://en.wikipedia.org/wiki/Northwind_Labs',
        retrieved_at: '2026-10-08T09:00:00Z',
        licence: 'CC-BY-SA-4.0',
        confidence: null,
      },
      {
        fact_key: 'ai_summary',
        value: 'A telecom billing software company.',
        origin: 'ai_inference',
        label: 'AI inference',
        source_name: 'ollama:qwen3:8b',
        source_url: null,
        retrieved_at: '2026-10-08T09:00:00Z',
        licence: null,
        confidence: null,
      },
    ],
    candidates: [],
    offers: [
      {
        job_opportunity_id: 9,
        title: 'Senior AI Engineer',
        source_url: 'https://jobs.example.test/9',
        first_seen_at: '2026-10-07T09:00:00Z',
        closed: false,
        fit_score: 82,
        recommendation: 'recommended',
        fit_band: 'excellent',
        state: 'unread',
        is_shortlisted: true,
        job_inbox_item_id: 90,
        version: 3,
      },
      {
        job_opportunity_id: 8,
        title: 'Old role',
        source_url: 'https://jobs.example.test/8',
        first_seen_at: '2026-08-07T09:00:00Z',
        closed: true,
        fit_score: null,
        recommendation: null,
        fit_band: null,
        state: null,
        is_shortlisted: false,
        job_inbox_item_id: null,
        version: null,
      },
      {
        job_opportunity_id: 7,
        title: 'Ignored role',
        source_url: 'https://jobs.example.test/7',
        first_seen_at: '2026-10-06T09:00:00Z',
        closed: false,
        fit_score: 58,
        recommendation: 'recommended',
        fit_band: 'average',
        state: 'ignored',
        is_shortlisted: false,
        job_inbox_item_id: 70,
        version: 2,
      },
    ],
    hiring: Array.from({ length: 12 }, (_, i) => ({
      week_start: `2026-07-${String(i + 1).padStart(2, '0')}`,
      new_offers: i % 3,
      open_offers: i,
    })),
    boards: [
      {
        source_configuration_id: 4,
        display_name: 'Northwind Careers',
        enabled: true,
        url: 'https://x',
      },
    ],
    warnings: [],
    ...overrides,
  }
}

let list: unknown[]
let detail: Record<string, unknown>

function renderPage(path = '/companies') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Companies />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('Companies screen', () => {
  beforeEach(() => {
    get.mockReset()
    post.mockReset()
    put.mockReset()
    del.mockReset()
    list = [
      company(1, 'Northwind Labs', { is_followed: true }),
      company(2, 'Contoso', { open_offers: 0, recommended_offers: 0, best_fit_score: null }),
    ]
    detail = dossier()
    get.mockImplementation((path: string) => {
      if (path === '/api/v1/companies')
        return Promise.resolve({
          data: {
            items: list,
            total: list.length,
            sort: 'fit',
            search_intent_id: 1,
            relevance_min_score: 45,
            recency_days: 30,
          },
        })
      if (path === '/api/v1/companies/{company_id}') return Promise.resolve({ data: detail })
      return Promise.reject(new Error(`unexpected GET ${path}`))
    })
  })

  it('lists followed companies first with their counted offers and best fit', async () => {
    renderPage()
    const northwind = await screen.findByRole('option', { name: /Northwind Labs/ })
    expect(within(northwind).getByText(/5 open/)).toBeInTheDocument()
    expect(within(northwind).getByText(/2 recommended/)).toBeInTheDocument()
    expect(within(northwind).getByLabelText('Best fit 82')).toBeInTheDocument()
    expect(screen.getByText('Followed')).toBeInTheDocument()
    expect(screen.getByText('All companies')).toBeInTheDocument()
    const contoso = screen.getByRole('option', { name: /Contoso/ })
    expect(within(contoso).getByText('No open offers')).toBeInTheDocument()
    expect(screen.getByText(/last 30 days/)).toBeInTheDocument()
    // "With open offers" is on by default, ignored companies are hidden, newest offers first.
    expect(get).toHaveBeenCalledWith(
      '/api/v1/companies',
      expect.objectContaining({
        params: { query: { limit: 50, sort: 'newest', hide_ignored: true, open_only: true } },
      }),
    )
  })

  it('folds and unfolds the Followed and All companies groups', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByRole('option', { name: /Northwind Labs/ })
    const followedHeader = screen.getByRole('button', { name: /^Followed/ })
    expect(followedHeader).toHaveAttribute('aria-expanded', 'true')
    await user.click(followedHeader)
    expect(followedHeader).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('option', { name: /Northwind Labs/ })).not.toBeInTheDocument()
    // The other group is untouched.
    expect(screen.getByRole('option', { name: /Contoso/ })).toBeInTheDocument()
    await user.click(followedHeader)
    expect(screen.getByRole('option', { name: /Northwind Labs/ })).toBeInTheDocument()
  })

  it('narrows the list with the filters and the search box', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByRole('option', { name: /Northwind Labs/ })
    await user.click(screen.getByRole('button', { name: 'With open offers' })) // turn off
    await user.click(screen.getByRole('button', { name: 'Recommended' }))
    await user.click(screen.getByRole('button', { name: 'Needs identification' }))
    await user.type(screen.getByRole('searchbox', { name: 'Search companies' }), 'north')
    const last = get.mock.calls.filter(([p]) => p === '/api/v1/companies').at(-1)![1]
    expect(last.params.query).toEqual({
      limit: 50,
      q: 'north',
      sort: 'newest',
      hide_ignored: true,
      recommended_only: true,
      pending_only: true,
    })
  })

  it('hides ignored companies by default and shows them on request', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByRole('option', { name: /Northwind Labs/ })
    const queryOf = () =>
      get.mock.calls.filter(([p]) => p === '/api/v1/companies').at(-1)![1].params.query
    expect(queryOf()).toMatchObject({ hide_ignored: true })
    await user.click(screen.getByRole('button', { name: 'Show ignored' }))
    await screen.findByRole('button', { name: 'Hide ignored' })
    expect(queryOf()).not.toHaveProperty('hide_ignored')
  })

  it('sorts the list by newest offers (default), most recommended, best fit or name', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByRole('option', { name: /Northwind Labs/ })
    const queryOf = () =>
      get.mock.calls.filter(([p]) => p === '/api/v1/companies').at(-1)![1].params.query
    const box = screen.getByRole('combobox', { name: 'Sort companies by' })
    expect(box).toHaveValue('newest')
    expect(queryOf()).toMatchObject({ sort: 'newest' })
    await user.selectOptions(box, 'Most recommended offers')
    await waitFor(() => expect(queryOf()).toMatchObject({ sort: 'recommended' }))
    await user.selectOptions(box, 'Name')
    await waitFor(() => expect(queryOf()).toMatchObject({ sort: 'name' }))
  })

  it('follows and unfollows a company from the list without opening it', async () => {
    const user = userEvent.setup()
    put.mockResolvedValue({ data: { company_id: 2, is_followed: true } })
    del.mockResolvedValue({ data: { company_id: 1, is_followed: false } })
    renderPage()
    await user.click(await screen.findByRole('button', { name: 'Follow Contoso' }))
    expect(put).toHaveBeenCalledWith('/api/v1/companies/{company_id}/follow', {
      params: { path: { company_id: 2 } },
    })
    await user.click(screen.getByRole('button', { name: 'Unfollow Northwind Labs' }))
    expect(del).toHaveBeenCalledWith('/api/v1/companies/{company_id}/follow', {
      params: { path: { company_id: 1 } },
    })
    expect(get.mock.calls.some(([p]) => p === '/api/v1/companies/{company_id}')).toBe(false)
  })

  it('shows the pending identification on a row', async () => {
    list = [company(3, 'Harbor Data', { pending_candidates: 3 })]
    renderPage()
    const row = await screen.findByRole('option', { name: /Harbor Data/ })
    expect(within(row).getByText('Identify')).toBeInTheDocument()
  })

  it('shows the dossier of the selected company with sourced facts and labels', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('option', { name: /Northwind Labs/ }))
    const panel = await screen.findByRole('region', { name: 'Northwind Labs' })
    expect(within(panel).getByRole('link', { name: /northwind\.example/ })).toHaveAttribute(
      'href',
      'https://www.northwind.example/',
    )
    expect(within(panel).getByText('software industry')).toBeInTheDocument()
    expect(within(panel).getByText(/wikidata · CC0-1\.0/)).toBeInTheDocument()
    expect(within(panel).getByText('AI inference')).toBeInTheDocument()
    expect(within(panel).getByText(/CC BY-SA/i)).toBeInTheDocument() // attribution for Wikipedia text
    expect(within(panel).getByRole('link', { name: 'Senior AI Engineer' })).toHaveAttribute(
      'href',
      'https://jobs.example.test/9',
    )
    expect(within(panel).getByRole('group', { name: /new offers per week/i })).toBeInTheDocument()
  })

  it('shows offers like the inbox and filters them; ignored ones stay, dimmed', async () => {
    const user = userEvent.setup()
    renderPage('/companies?company=1')
    const panel = await screen.findByRole('region', { name: 'Northwind Labs' })
    const offers = within(panel)
      .getByRole('heading', { name: /^Offers/ })
      .closest('section')!
    expect(within(offers).getByText('82')).toBeInTheDocument()
    expect(within(offers).getByText('Excellent')).toBeInTheDocument()
    expect(within(offers).getByLabelText('Shortlisted')).toBeInTheDocument()
    expect(within(offers).getByText('NEW')).toBeInTheDocument()
    expect(within(offers).getByText('ignored')).toBeInTheDocument()
    expect(within(offers).queryByText('Old role')).not.toBeInTheDocument() // closed: hidden by default
    await user.click(within(offers).getByRole('button', { name: 'Hide ignored' }))
    expect(within(offers).queryByText('Ignored role')).not.toBeInTheDocument()
    await user.click(within(offers).getByRole('button', { name: 'Closed' }))
    expect(within(offers).getByText('Old role')).toBeInTheDocument()
    expect(within(offers).getByText('Pending')).toBeInTheDocument()
    await user.click(within(offers).getByRole('button', { name: 'Recommended' }))
    expect(within(offers).queryByText('Old role')).not.toBeInTheDocument()
  })

  it('sorts the offers by age or by fit score', async () => {
    const user = userEvent.setup()
    renderPage('/companies?company=1')
    const panel = await screen.findByRole('region', { name: 'Northwind Labs' })
    const offers = within(panel).getByRole('region', { name: /^Offers/ })
    const titles = () =>
      within(offers)
        .getAllByRole('listitem')
        .map((li) => li.getAttribute('aria-label'))
    const sortBy = (label: string) =>
      user.selectOptions(within(offers).getByRole('combobox', { name: 'Sort by' }), label)

    await sortBy('Oldest first')
    expect(titles()).toEqual(['Ignored role', 'Senior AI Engineer'])
    await sortBy('Newest first')
    expect(titles()).toEqual(['Senior AI Engineer', 'Ignored role'])
    await sortBy('Lowest fit')
    expect(titles()).toEqual(['Ignored role', 'Senior AI Engineer'])
    await sortBy('Highest fit')
    expect(titles()).toEqual(['Senior AI Engineer', 'Ignored role'])
  })

  describe('triage from the dossier', () => {
    async function openOffers() {
      const user = userEvent.setup()
      renderPage('/companies?company=1')
      const panel = await screen.findByRole('region', { name: 'Northwind Labs' })
      const offers = within(panel).getByRole('region', { name: /^Offers/ })
      return { user, offers }
    }
    const inboxCall = (itemId: number, action: string, version: number) => [
      '/api/v1/inbox/{job_inbox_item_id}/actions',
      {
        params: { path: { job_inbox_item_id: itemId }, query: {} },
        body: { action, expected_version: version },
      },
    ]

    beforeEach(() => {
      post.mockImplementation(() => Promise.resolve({ data: { item: { version: 4 }, undo: null } }))
    })

    it('shortlists, ignores, archives and marks applied one offer at a time', async () => {
      const { user, offers } = await openOffers()
      const row = within(offers).getByRole('listitem', { name: /Senior AI Engineer/ })
      await user.click(within(row).getByRole('button', { name: 'Ignore Senior AI Engineer' }))
      expect(post).toHaveBeenLastCalledWith(...inboxCall(90, 'ignore', 3))
      await user.click(within(row).getByRole('button', { name: 'Archive Senior AI Engineer' }))
      expect(post).toHaveBeenLastCalledWith(...inboxCall(90, 'archive', 3))
      await user.click(
        within(row).getByRole('button', { name: 'Mark Senior AI Engineer as applied' }),
      )
      expect(post).toHaveBeenLastCalledWith(...inboxCall(90, 'record_application', 3))
    })

    it('toggles the shortlist star with a label that names the offer', async () => {
      const { user, offers } = await openOffers()
      // Offer 9 is shortlisted: the button removes it; offer 7 is not, so it adds it.
      await user.click(
        within(offers).getByRole('button', { name: 'Remove Senior AI Engineer from shortlist' }),
      )
      expect(post).toHaveBeenLastCalledWith(...inboxCall(90, 'unshortlist', 3))
      await user.click(
        within(offers).getByRole('button', { name: 'Add Ignored role to shortlist' }),
      )
      expect(post).toHaveBeenLastCalledWith(...inboxCall(70, 'shortlist', 2))
    })

    it('offers only Restore on an ignored offer', async () => {
      const { user, offers } = await openOffers()
      const row = within(offers).getByRole('listitem', { name: /Ignored role/ })
      expect(within(row).queryByRole('button', { name: /^Ignore / })).not.toBeInTheDocument()
      expect(within(row).queryByRole('button', { name: /^Archive / })).not.toBeInTheDocument()
      await user.click(within(row).getByRole('button', { name: 'Restore Ignored role' }))
      expect(post).toHaveBeenLastCalledWith(...inboxCall(70, 'restore', 2))
    })

    it('shows no actions for an offer the owner has no inbox item for', async () => {
      const { user, offers } = await openOffers()
      await user.click(within(offers).getByRole('button', { name: 'Closed' }))
      const row = within(offers).getByRole('listitem', { name: /Old role/ })
      expect(within(row).queryByRole('button')).not.toBeInTheDocument()
    })

    it('confirms the action, undoes it and refreshes the dossier and the list', async () => {
      const { user, offers } = await openOffers()
      const loads = () =>
        get.mock.calls.filter(([path]) => path === '/api/v1/companies/{company_id}')
      const before = loads().length
      await user.click(within(offers).getByRole('button', { name: 'Ignore Senior AI Engineer' }))
      const status = await screen.findByRole('status')
      expect(status).toHaveTextContent('Ignored')
      await vi.waitFor(() => expect(loads().length).toBeGreaterThan(before))
      // The offer was unread, so taking it back restores it and marks it unread again, in order
      // and with the version each step returned.
      post.mockClear()
      await user.click(within(status).getByRole('button', { name: 'Undo' }))
      await vi.waitFor(() => expect(post).toHaveBeenCalledTimes(2))
      expect(post).toHaveBeenNthCalledWith(1, ...inboxCall(90, 'restore', 4))
      expect(post).toHaveBeenNthCalledWith(2, ...inboxCall(90, 'mark_unread', 4))
    })

    it('says so when an action fails, for example on a version conflict', async () => {
      post.mockImplementation(() =>
        Promise.resolve({
          error: { error: { code: 'version_conflict', message: 'Changed elsewhere.' } },
        }),
      )
      const { user, offers } = await openOffers()
      await user.click(within(offers).getByRole('button', { name: 'Archive Senior AI Engineer' }))
      expect(await within(offers).findByRole('alert')).toBeInTheDocument()
    })
  })

  it('says when only the best offers are shown', async () => {
    detail = dossier({ offers_truncated: true })
    renderPage('/companies?company=1')
    expect(await screen.findByText(/showing the 3 best-fitting offers/i)).toBeInTheDocument()
  })

  it('asks for older offers on request and follows from the dossier', async () => {
    const user = userEvent.setup()
    put.mockResolvedValue({ data: { company_id: 1, is_followed: true } })
    detail = dossier({ is_followed: false })
    renderPage('/companies?company=1')
    const panel = await screen.findByRole('region', { name: 'Northwind Labs' })
    await user.click(within(panel).getByRole('button', { name: /older than 30 days/i }))
    const last = get.mock.calls.filter(([p]) => p === '/api/v1/companies/{company_id}').at(-1)![1]
    expect(last.params.query).toEqual({ include_older: true })
    await user.click(within(panel).getByRole('button', { name: 'Follow Northwind Labs' }))
    expect(put).toHaveBeenCalledWith('/api/v1/companies/{company_id}/follow', {
      params: { path: { company_id: 1 } },
    })
  })

  it('ignores and stops ignoring a company from the dossier', async () => {
    const user = userEvent.setup()
    put.mockResolvedValue({ data: { company_id: 1, is_ignored: true } })
    del.mockResolvedValue({ data: { company_id: 1, is_ignored: false } })
    detail = dossier({ is_ignored: false })
    renderPage('/companies?company=1')
    const panel = await screen.findByRole('region', { name: 'Northwind Labs' })
    put.mockImplementation(() => {
      detail = dossier({ is_ignored: true }) // the server now ignores it
      return Promise.resolve({ data: { company_id: 1, is_ignored: true } })
    })
    await user.click(within(panel).getByRole('button', { name: 'Ignore company' }))
    expect(put).toHaveBeenCalledWith('/api/v1/companies/{company_id}/ignore', {
      params: { path: { company_id: 1 } },
    })
    await user.click(await within(panel).findByRole('button', { name: 'Stop ignoring company' }))
    expect(del).toHaveBeenCalledWith('/api/v1/companies/{company_id}/ignore', {
      params: { path: { company_id: 1 } },
    })
  })

  it('marks an ignored company in the list with text', async () => {
    list = [company(1, 'Northwind Labs', { is_ignored: true }), company(2, 'Contoso')]
    renderPage('/companies')
    const row = (await screen.findByText('Northwind Labs')).closest('[role="option"]')!
    expect(within(row as HTMLElement).getByText('Ignored')).toBeInTheDocument()
  })

  it('looks a stale company up in the public sources once, by itself', async () => {
    detail = dossier({ stale: true, enriched_at: null, facts: [] })
    post.mockImplementation(() => {
      detail = dossier() // the server now knows the facts
      return Promise.resolve({ data: detail })
    })
    renderPage('/companies?company=1')
    expect(await screen.findByText('software industry')).toBeInTheDocument()
    expect(post).toHaveBeenCalledTimes(1)
    expect(post).toHaveBeenCalledWith('/api/v1/companies/{company_id}/enrich', {
      params: { path: { company_id: 1 } },
    })
  })

  it('offers pending candidates for the owner to confirm or reject', async () => {
    const user = userEvent.setup()
    detail = dossier({
      candidates: [
        {
          company_enrichment_candidate_id: 7,
          source_name: 'wikidata',
          external_id: 'Q99',
          label: 'Northwind Traders',
          description: 'trading company',
          website: 'https://traders.example',
        },
      ],
    })
    post.mockImplementation(() => Promise.resolve({ data: detail }))
    renderPage('/companies?company=1')
    const card = (await screen.findByRole('heading', { name: /is this the company/i })).closest(
      'section',
    )!
    expect(within(card).getByText('Northwind Traders')).toBeInTheDocument()
    // The owner can open the Wikidata entry to tell look-alike candidates apart.
    const link = within(card).getByRole('link', { name: /wikidata.*northwind traders/i })
    expect(link).toHaveAttribute('href', 'https://www.wikidata.org/wiki/Q99')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'))
    await user.click(within(card).getByRole('button', { name: 'Yes, this is it' }))
    expect(post).toHaveBeenCalledWith(
      '/api/v1/companies/{company_id}/candidates/{company_enrichment_candidate_id}/confirm',
      { params: { path: { company_id: 1, company_enrichment_candidate_id: 7 } } },
    )
    await user.click(within(card).getByRole('button', { name: 'No' }))
    expect(post).toHaveBeenLastCalledWith(
      '/api/v1/companies/{company_id}/candidates/{company_enrichment_candidate_id}/reject',
      { params: { path: { company_id: 1, company_enrichment_candidate_id: 7 } } },
    )
  })

  it('writes an AI summary on request and reports why it cannot', async () => {
    const user = userEvent.setup()
    post.mockResolvedValue({
      error: {
        error: {
          code: 'validation_error',
          message: 'Choose a local model for job analysis in AI & privacy to write summaries.',
          details: {},
        },
      },
      response: { status: 422 },
    })
    renderPage('/companies?company=1')
    await user.click(await screen.findByRole('button', { name: 'Write AI summary' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/local model/i)
  })

  it('says so when no company has open offers and when there is no company yet', async () => {
    const user = userEvent.setup()
    list = []
    renderPage()
    expect(await screen.findByText(/no company has open offers/i)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'With open offers' })) // turn off
    expect(await screen.findByText(/no companies yet/i)).toBeInTheDocument()
  })
})
