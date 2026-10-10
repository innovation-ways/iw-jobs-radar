import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Companies } from './Companies'

const get = vi.fn()
const post = vi.fn()
vi.mock('@/api/client', () => ({
  api: { GET: (...a: unknown[]) => get(...a), POST: (...a: unknown[]) => post(...a) },
}))

function company(id: number, name: string, overrides: Record<string, unknown> = {}) {
  return {
    company_id: id,
    name,
    homepage_url: null,
    careers_url: null,
    employer_type: null,
    open_offers: 5,
    new_offers_7d: 1,
    new_offers_15d: 3,
    new_offers_30d: 4,
    relevant_new_offers_7d: 0,
    relevant_new_offers_15d: 2,
    relevant_new_offers_30d: 2,
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
      },
      {
        job_opportunity_id: 8,
        title: 'Old role',
        source_url: 'https://jobs.example.test/8',
        first_seen_at: '2026-08-07T09:00:00Z',
        closed: true,
        fit_score: null,
        recommendation: null,
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
    list = [
      company(1, 'Northwind Labs'),
      company(2, 'Contoso', { new_offers_15d: 0, relevant_new_offers_15d: 0 }),
    ]
    detail = dossier()
    get.mockImplementation((path: string) => {
      if (path === '/api/v1/companies')
        return Promise.resolve({
          data: {
            items: list,
            total: list.length,
            window: 15,
            sort: 'new',
            search_intent_id: 1,
            relevance_min_score: 45,
          },
        })
      if (path === '/api/v1/companies/{company_id}') return Promise.resolve({ data: detail })
      return Promise.reject(new Error(`unexpected GET ${path}`))
    })
  })

  it('lists companies with new offers for the chosen window', async () => {
    renderPage()
    const northwind = await screen.findByRole('option', { name: /Northwind Labs/ })
    expect(within(northwind).getByText('3 new')).toBeInTheDocument()
    expect(within(northwind).getByText('2 relevant')).toBeInTheDocument()
    expect(get).toHaveBeenCalledWith(
      '/api/v1/companies',
      expect.objectContaining({
        params: { query: expect.objectContaining({ window: 15, sort: 'new', limit: 50 }) },
      }),
    )
  })

  it('changes the window and the relevant-only filter, and searches', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByRole('option', { name: /Northwind Labs/ })
    await user.click(screen.getByRole('button', { name: '30 d' }))
    await user.click(screen.getByLabelText(/only offers relevant/i))
    await user.type(screen.getByRole('searchbox', { name: 'Search companies' }), 'north')
    const last = get.mock.calls.filter(([p]) => p === '/api/v1/companies').at(-1)![1]
    expect(last.params.query).toMatchObject({ window: 30, relevant_only: true, q: 'north' })
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
    expect(within(panel).getByText('Fit 82')).toBeInTheDocument()
    expect(within(panel).getByText('Closed')).toBeInTheDocument()
    expect(within(panel).getByRole('img', { name: /weekly new offers/i })).toBeInTheDocument()
  })

  it('looks a stale company up in the public sources once, by itself', async () => {
    detail = dossier({ stale: true, enriched_at: null, facts: [] })
    post.mockResolvedValue({ data: dossier() })
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

  it('says so when there is no company yet', async () => {
    list = []
    renderPage()
    expect(await screen.findByText(/no companies yet/i)).toBeInTheDocument()
  })
})
