import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Sources } from './Sources'

const get = vi.fn()
const post = vi.fn()
const put = vi.fn()
const del = vi.fn()
vi.mock('@/api/client', () => ({
  api: {
    GET: (...args: unknown[]) => get(...args),
    POST: (...args: unknown[]) => post(...args),
    PUT: (...args: unknown[]) => put(...args),
    DELETE: (...args: unknown[]) => del(...args),
  },
}))

const FILTERS = {
  schema_version: 1,
  categories: ['software', 'data', 'devops', 'security', 'telecom'],
  search_terms: [] as string[],
  max_age_days: 30,
  max_postings_per_run: 500,
}

const result = {
  collection_run_id: 7,
  source_configuration_id: 10,
  outcome: 'success',
  started_at: '2026-10-09T07:30:00Z',
  finished_at: '2026-10-09T07:30:05Z',
  collected_count: 212,
  new_count: 8,
  updated_count: 3,
  deduplicated_count: 200,
  closed_count: 0,
  dropped_count: 40,
  http_status: 200,
  error_class: null,
  error_message: null,
  duration_ms: 5000,
}

function board(overrides: Record<string, unknown> = {}) {
  return {
    source_configuration_id: 10,
    source_type: 'himalayas',
    external_identifier: 'himalayas',
    display_name: 'Himalayas',
    company_id: null,
    company_name: null,
    url: 'https://himalayas.app/jobs/api',
    enabled: true,
    rate_limit_per_minute: 30,
    version: 2,
    open_postings: 212,
    last_result: result,
    category: 'job_board',
    coverage_note: 'Remote · eligible countries listed per job',
    filters: FILTERS,
    credential_status: 'not_needed',
    credential_updated_at: null,
    terms_url: 'https://himalayas.app/docs/remote-jobs-api',
    attribution_text: 'Jobs from Himalayas (himalayas.app).',
    next_run_allowed_at: null,
    ...overrides,
  }
}

const company = {
  ...board({
    source_configuration_id: 1,
    source_type: 'greenhouse',
    external_identifier: 'acme',
    display_name: 'Acme Robotics',
    company_id: 1,
    company_name: 'Acme Robotics',
    category: 'company_board',
    coverage_note: null,
    filters: null,
    terms_url: null,
    attribution_text: null,
    last_result: { ...result, source_configuration_id: 1 },
  }),
}

function entry(key: string, name: string, extra: Record<string, unknown> = {}) {
  return {
    catalogue_key: key,
    display_name: name,
    coverage_note: `${name} coverage`,
    homepage_url: `https://${key}.example.test`,
    requires_credential: false,
    credential_label: null,
    terms_note: `${name} terms note`,
    terms_url: `https://${key}.example.test/terms`,
    terms_read_on: '2026-10-09',
    attribution_text: `Jobs from ${name}.`,
    delay_note: null,
    min_interval_minutes: 60,
    default_filters: FILTERS,
    available_categories: ['software', 'data', 'devops', 'security', 'telecom'],
    already_added: false,
    ...extra,
  }
}

const catalogue = [
  entry('arbeitnow', 'Arbeitnow'),
  entry('himalayas', 'Himalayas', { already_added: true }),
  entry('itjobs_pt', 'ITJobs.pt', {
    requires_credential: true,
    credential_label: 'ITJobs API key',
  }),
]

const scope = {
  configured: true,
  country_codes: ['PT', 'ES'],
  include_worldwide: true,
  any_country: false,
  onsite_areas: [{ place: 'Lisbon, Portugal', radius_km: 40 }],
}
const schedule = {
  run_time_local: '07:30',
  timezone: 'Europe/Lisbon',
  enabled: false,
  version: 1,
  next_run_at: null,
  next_run_local: null,
}

let sources: unknown[]
let currentScope: typeof scope

function envelope(message: string, errorClass?: string) {
  return {
    error: {
      error: { code: 'x', message, details: errorClass ? { error_class: errorClass } : {} },
    },
    response: { status: 422 },
  }
}

function renderSources() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <Sources />
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

async function jobBoards() {
  return within(await screen.findByRole('region', { name: 'Job boards' }))
}

describe('Job boards section', () => {
  beforeEach(() => {
    get.mockReset()
    post.mockReset()
    put.mockReset()
    del.mockReset()
    sources = [company, board()]
    currentScope = scope
    get.mockImplementation((path: string) => {
      if (path === '/api/v1/sources') return Promise.resolve({ data: { items: sources } })
      if (path === '/api/v1/collection-runs')
        return Promise.resolve({ data: { items: [], next_before_collection_run_id: null } })
      if (path === '/api/v1/settings/schedule') return Promise.resolve({ data: schedule })
      if (path === '/api/v1/source-catalogue')
        return Promise.resolve({ data: { items: catalogue } })
      if (path === '/api/v1/source-scope') return Promise.resolve({ data: currentScope })
      return Promise.reject(new Error(`unexpected GET ${path}`))
    })
  })

  it('keeps company boards and job boards in separate sections', async () => {
    renderSources()
    const boards = await jobBoards()
    expect(
      within(await screen.findByRole('region', { name: 'Company boards' })).getByText(
        'Acme Robotics',
      ),
    ).toBeInTheDocument()
    const row = boards.getByRole('row', { name: /Himalayas/ })
    expect(within(row).getByText('Remote · eligible countries listed per job')).toBeInTheDocument()
    expect(within(row).getByText('Succeeded')).toBeInTheDocument()
    expect(within(row).getByText('212')).toBeInTheDocument()
    expect(boards.queryByText('Acme Robotics')).not.toBeInTheDocument()
  })

  it('shows where the boards look, taken from the profile, with a link to change it', async () => {
    renderSources()
    const boards = await jobBoards()
    const note = await boards.findByText(/from your profile and search intents/i)
    expect(note.textContent).toMatch(/Portugal/)
    expect(note.textContent).toMatch(/Spain/)
    expect(note.textContent).toMatch(/remote work from anywhere|worldwide/i)
    expect(note.textContent).toMatch(/on site within 40 km of Lisbon, Portugal/)
    expect(boards.getByRole('link', { name: /Profile & intent/ })).toHaveAttribute(
      'href',
      '/profile',
    )
  })

  it('asks for a location when the profile and intents give none', async () => {
    currentScope = {
      configured: false,
      country_codes: [],
      include_worldwide: false,
      any_country: false,
      onsite_areas: [],
    }
    renderSources()
    const boards = await jobBoards()
    expect(await boards.findByRole('alert')).toHaveTextContent(/set your base location/i)
  })

  it('says what an empty list means', async () => {
    sources = [company]
    renderSources()
    expect(await (await jobBoards()).findByText(/No job boards yet/i)).toBeInTheDocument()
  })

  it('shows partial and skipped runs in words', async () => {
    sources = [
      board({ last_result: { ...result, outcome: 'partial' } }),
      board({
        source_configuration_id: 11,
        display_name: 'Jobicy',
        source_type: 'jobicy',
        external_identifier: 'jobicy',
        last_result: { ...result, source_configuration_id: 11, outcome: 'skipped' },
      }),
    ]
    renderSources()
    const boards = await jobBoards()
    expect(await boards.findByText('Partial: limit reached')).toBeInTheDocument()
    expect(boards.getByText('Skipped: ran recently')).toBeInTheDocument()
  })

  it('disables Run now until the board may be contacted again and says when', async () => {
    sources = [board({ next_run_allowed_at: '2999-01-01T10:00:00Z' })]
    renderSources()
    const boards = await jobBoards()
    expect(await boards.findByRole('button', { name: 'Run Himalayas now' })).toBeDisabled()
    expect(boards.getByText(/Next run allowed/)).toBeInTheDocument()
  })
})

describe('Adding a job board', () => {
  beforeEach(() => {
    get.mockReset()
    post.mockReset()
    sources = [company]
    currentScope = scope
    get.mockImplementation((path: string) => {
      if (path === '/api/v1/sources') return Promise.resolve({ data: { items: sources } })
      if (path === '/api/v1/collection-runs')
        return Promise.resolve({ data: { items: [], next_before_collection_run_id: null } })
      if (path === '/api/v1/settings/schedule') return Promise.resolve({ data: schedule })
      if (path === '/api/v1/source-catalogue')
        return Promise.resolve({ data: { items: catalogue } })
      if (path === '/api/v1/source-scope') return Promise.resolve({ data: currentScope })
      return Promise.reject(new Error(`unexpected GET ${path}`))
    })
  })

  async function openForm(name: string) {
    const user = userEvent.setup()
    renderSources()
    const boards = await jobBoards()
    await user.click(await boards.findByRole('button', { name: 'Add a job board' }))
    await user.click(await boards.findByRole('button', { name: `Add ${name}` }))
    return { user, boards }
  }

  it('lists the catalogue with coverage and terms, and marks boards already added', async () => {
    const user = userEvent.setup()
    renderSources()
    const boards = await jobBoards()
    await user.click(await boards.findByRole('button', { name: 'Add a job board' }))
    const list = await boards.findByRole('list', { name: 'Job board catalogue' })
    expect(within(list).getByText('Arbeitnow coverage')).toBeInTheDocument()
    expect(within(list).getByText('Himalayas terms note')).toBeInTheDocument()
    expect(within(list).getByText(/Added/)).toBeInTheDocument()
    expect(within(list).queryByRole('button', { name: 'Add Himalayas' })).not.toBeInTheDocument()
    expect(within(list).getByText(/Needs a free key/i)).toBeInTheDocument()
  })

  it('previews the matches before adding and adds with the filters that were previewed', async () => {
    const { user, boards } = await openForm('Arbeitnow')
    const add = boards.getByRole('button', { name: 'Add Arbeitnow to my sources' })
    expect(add).toBeDisabled() // nothing was checked yet
    post.mockResolvedValueOnce({
      data: {
        display_name: 'Arbeitnow',
        postings_total: 1398,
        postings_matching: 212,
        matching_is_lower_bound: false,
      },
    })
    await user.click(boards.getByRole('button', { name: 'Check & preview' }))
    expect(post).toHaveBeenCalledWith('/api/v1/sources/preview', {
      body: { catalogue_key: 'arbeitnow', filters: FILTERS },
    })
    expect(await boards.findByText(/212 of 1,398 postings match/)).toBeInTheDocument()
    expect(add).toBeEnabled()

    post.mockResolvedValueOnce({ data: board({ display_name: 'Arbeitnow' }) })
    await user.click(add)
    expect(post).toHaveBeenLastCalledWith('/api/v1/sources', {
      body: {
        source_type: 'arbeitnow',
        external_identifier: 'arbeitnow',
        enabled: true,
        filters: FILTERS,
      },
    })
    expect(await boards.findByText(/Added Arbeitnow/)).toBeInTheDocument()
  })

  it('invalidates the preview when a filter changes', async () => {
    const { user, boards } = await openForm('Arbeitnow')
    post.mockResolvedValueOnce({
      data: {
        display_name: 'Arbeitnow',
        postings_total: 10,
        postings_matching: 3,
        matching_is_lower_bound: false,
      },
    })
    await user.click(boards.getByRole('button', { name: 'Check & preview' }))
    const add = boards.getByRole('button', { name: 'Add Arbeitnow to my sources' })
    await boards.findByText(/3 of 10 postings match/)
    expect(add).toBeEnabled()
    await user.click(boards.getByRole('checkbox', { name: 'devops' }))
    expect(add).toBeDisabled()
    expect(boards.queryByText(/3 of 10 postings match/)).not.toBeInTheDocument()
  })

  it('says when the count is a lower bound', async () => {
    const { user, boards } = await openForm('Arbeitnow')
    post.mockResolvedValueOnce({
      data: {
        display_name: 'Arbeitnow',
        postings_total: 1398,
        postings_matching: 100,
        matching_is_lower_bound: true,
      },
    })
    await user.click(boards.getByRole('button', { name: 'Check & preview' }))
    expect(await boards.findByText(/at least 100/)).toBeInTheDocument()
  })

  it('asks for the key when the board needs one, hides it, and sends it once', async () => {
    const { user, boards } = await openForm('ITJobs.pt')
    const field = boards.getByLabelText('ITJobs API key')
    expect(field).toHaveAttribute('type', 'password')
    expect(boards.getByRole('button', { name: 'Check & preview' })).toBeDisabled()
    await user.type(field, 'the-key')
    post.mockResolvedValueOnce({
      data: {
        display_name: 'ITJobs.pt',
        postings_total: 50,
        postings_matching: 9,
        matching_is_lower_bound: false,
      },
    })
    await user.click(boards.getByRole('button', { name: 'Check & preview' }))
    expect(post).toHaveBeenCalledWith('/api/v1/sources/preview', {
      body: { catalogue_key: 'itjobs_pt', filters: FILTERS, credential: 'the-key' },
    })
    post.mockResolvedValueOnce({ data: board({ display_name: 'ITJobs.pt' }) })
    await user.click(await boards.findByRole('button', { name: 'Add ITJobs.pt to my sources' }))
    expect(await boards.findByText(/Added ITJobs\.pt/)).toBeInTheDocument()
    expect(screen.queryByDisplayValue('the-key')).not.toBeInTheDocument()
  })

  it('shows a refused key and keeps Add disabled', async () => {
    const { user, boards } = await openForm('ITJobs.pt')
    await user.type(boards.getByLabelText('ITJobs API key'), 'bad')
    post.mockResolvedValueOnce(envelope('The source refused the credential.', 'authentication'))
    await user.click(boards.getByRole('button', { name: 'Check & preview' }))
    expect(await boards.findByRole('alert')).toHaveTextContent(/refused the credential/)
    expect(boards.getByRole('button', { name: 'Add ITJobs.pt to my sources' })).toBeDisabled()
  })

  it('cannot preview without a location from the profile', async () => {
    currentScope = {
      configured: false,
      country_codes: [],
      include_worldwide: false,
      any_country: false,
      onsite_areas: [],
    }
    const { boards } = await openForm('Arbeitnow')
    expect(boards.getByRole('button', { name: 'Check & preview' })).toBeDisabled()
  })
})

describe('Job board settings', () => {
  beforeEach(() => {
    get.mockReset()
    put.mockReset()
    del.mockReset()
    sources = [
      board(),
      board({
        source_configuration_id: 12,
        source_type: 'itjobs_pt',
        external_identifier: 'itjobs_pt',
        display_name: 'ITJobs.pt',
        credential_status: 'saved',
        credential_updated_at: '2026-10-09T08:00:00Z',
      }),
    ]
    currentScope = scope
    get.mockImplementation((path: string) => {
      if (path === '/api/v1/sources') return Promise.resolve({ data: { items: sources } })
      if (path === '/api/v1/collection-runs')
        return Promise.resolve({ data: { items: [], next_before_collection_run_id: null } })
      if (path === '/api/v1/settings/schedule') return Promise.resolve({ data: schedule })
      if (path === '/api/v1/source-catalogue')
        return Promise.resolve({
          data: { items: catalogue.map((c) => ({ ...c, already_added: true })) },
        })
      if (path === '/api/v1/source-scope') return Promise.resolve({ data: currentScope })
      return Promise.reject(new Error(`unexpected GET ${path}`))
    })
  })

  it('opens a settings panel with the terms, attribution and the filters', async () => {
    const user = userEvent.setup()
    renderSources()
    const boards = await jobBoards()
    const toggle = await boards.findByRole('button', { name: 'Settings for Himalayas' })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    await user.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(boards.getByLabelText('Posted within (days)')).toHaveValue(30)
    expect(boards.getByRole('link', { name: /Terms/ })).toHaveAttribute(
      'href',
      'https://himalayas.app/docs/remote-jobs-api',
    )
    expect(boards.getByText('Jobs from Himalayas (himalayas.app).')).toBeInTheDocument()
  })

  it('saves changed filters with the version the owner saw', async () => {
    const user = userEvent.setup()
    renderSources()
    const boards = await jobBoards()
    await user.click(await boards.findByRole('button', { name: 'Settings for Himalayas' }))
    const days = boards.getByLabelText('Posted within (days)')
    await user.clear(days)
    await user.type(days, '7')
    put.mockResolvedValue({ data: board({ version: 3 }) })
    await user.click(boards.getByRole('button', { name: 'Save filters' }))
    expect(put).toHaveBeenCalledWith('/api/v1/sources/{source_configuration_id}', {
      params: { path: { source_configuration_id: 10 } },
      body: { expected_version: 2, filters: { ...FILTERS, max_age_days: 7 } },
    })
  })

  it('replaces and removes a saved key without ever showing it', async () => {
    const user = userEvent.setup()
    renderSources()
    const boards = await jobBoards()
    await user.click(await boards.findByRole('button', { name: 'Settings for ITJobs.pt' }))
    expect(boards.getByText(/Key: saved/)).toBeInTheDocument()
    const field = boards.getByLabelText('ITJobs API key')
    expect(field).toHaveAttribute('placeholder', '•••••• (replace)')
    await user.type(field, 'new-key')
    put.mockResolvedValue({ data: board({ source_configuration_id: 12 }) })
    await user.click(boards.getByRole('button', { name: 'Replace key' }))
    expect(put).toHaveBeenCalledWith('/api/v1/sources/{source_configuration_id}/credential', {
      params: { path: { source_configuration_id: 12 } },
      body: { secret: 'new-key' },
    })
    del.mockResolvedValue({
      data: board({ source_configuration_id: 12, credential_status: 'none', enabled: false }),
    })
    await user.click(boards.getByRole('button', { name: 'Remove key' }))
    expect(del).toHaveBeenCalledWith('/api/v1/sources/{source_configuration_id}/credential', {
      params: { path: { source_configuration_id: 12 } },
    })
  })
})

describe('Company board filters', () => {
  beforeEach(() => {
    get.mockReset()
    put.mockReset()
    sources = [
      company,
      {
        ...company,
        source_configuration_id: 2,
        display_name: 'Contoso',
        company_name: 'Contoso',
        external_identifier: 'contoso',
        filters: { ...FILTERS, categories: ['software'] },
        version: 4,
      },
    ]
    currentScope = scope
    get.mockImplementation((path: string) => {
      if (path === '/api/v1/sources') return Promise.resolve({ data: { items: sources } })
      if (path === '/api/v1/collection-runs')
        return Promise.resolve({ data: { items: [], next_before_collection_run_id: null } })
      if (path === '/api/v1/settings/schedule') return Promise.resolve({ data: schedule })
      if (path === '/api/v1/source-catalogue')
        return Promise.resolve({ data: { items: catalogue } })
      if (path === '/api/v1/source-scope') return Promise.resolve({ data: currentScope })
      return Promise.reject(new Error(`unexpected GET ${path}`))
    })
  })

  async function open(name: string) {
    const user = userEvent.setup()
    renderSources()
    const boards = within(await screen.findByRole('region', { name: 'Company boards' }))
    await user.click(await boards.findByRole('button', { name: `Filters for ${name}` }))
    return { user, boards }
  }

  it('keeps every posting until the owner opts in', async () => {
    const { boards } = await open('Acme Robotics')
    const toggle = boards.getByRole('checkbox', { name: /keep only postings that match/i })
    expect(toggle).not.toBeChecked()
    expect(boards.queryByLabelText('Posted within (days)')).not.toBeInTheDocument()
    expect(boards.getByText(/every posting is kept/i)).toBeInTheDocument()
  })

  it('opts in with the default filters and saves with the version the owner saw', async () => {
    const { user, boards } = await open('Acme Robotics')
    await user.click(boards.getByRole('checkbox', { name: /keep only postings that match/i }))
    expect(boards.getByLabelText('Posted within (days)')).toHaveValue(30)
    expect(boards.getByText(/from your profile and search intents/i)).toBeInTheDocument()
    put.mockResolvedValue({ data: company })
    await user.click(boards.getByRole('button', { name: 'Save filters' }))
    expect(put).toHaveBeenCalledWith('/api/v1/sources/{source_configuration_id}', {
      params: { path: { source_configuration_id: 1 } },
      body: { expected_version: 2, filters: FILTERS },
    })
  })

  it('shows saved filters and opts out with clear_filters', async () => {
    const { user, boards } = await open('Contoso')
    const toggle = boards.getByRole('checkbox', { name: /keep only postings that match/i })
    expect(toggle).toBeChecked()
    expect(boards.getByRole('checkbox', { name: 'devops' })).not.toBeChecked()
    await user.click(toggle)
    put.mockResolvedValue({ data: company })
    await user.click(boards.getByRole('button', { name: 'Save filters' }))
    expect(put).toHaveBeenCalledWith('/api/v1/sources/{source_configuration_id}', {
      params: { path: { source_configuration_id: 2 } },
      body: { expected_version: 4, clear_filters: true },
    })
  })

  it('cannot save until something changed', async () => {
    const { boards } = await open('Contoso')
    expect(boards.getByRole('button', { name: 'Save filters' })).toBeDisabled()
  })
})
