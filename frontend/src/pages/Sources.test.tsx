import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Sources } from './Sources'

const get = vi.fn()
const post = vi.fn()
const put = vi.fn()
vi.mock('@/api/client', () => ({
  api: {
    GET: (...args: unknown[]) => get(...args),
    POST: (...args: unknown[]) => post(...args),
    PUT: (...args: unknown[]) => put(...args),
  },
}))

const result = {
  collection_run_id: 7,
  source_configuration_id: 1,
  outcome: 'success',
  started_at: '2026-10-08T07:30:00Z',
  finished_at: '2026-10-08T07:30:05Z',
  collected_count: 42,
  new_count: 5,
  updated_count: 2,
  deduplicated_count: 35,
  closed_count: 1,
  http_status: 200,
  error_class: null,
  error_message: null,
  duration_ms: 5000,
}

function source(overrides: Record<string, unknown> = {}) {
  return {
    source_configuration_id: 1,
    source_type: 'greenhouse',
    external_identifier: 'acme',
    display_name: 'Acme Robotics',
    company_id: 1,
    company_name: 'Acme Robotics',
    url: 'https://boards.example.test/v1/boards/acme/jobs',
    enabled: true,
    rate_limit_per_minute: 6,
    version: 1,
    open_postings: 41,
    last_result: result,
    ...overrides,
  }
}

const failed = source({
  source_configuration_id: 2,
  display_name: 'Contoso',
  company_name: 'Contoso',
  external_identifier: 'contoso',
  open_postings: 0,
  last_result: {
    ...result,
    source_configuration_id: 2,
    outcome: 'failed',
    collected_count: 0,
    new_count: 0,
    updated_count: 0,
    error_class: 'not_found',
    error_message: 'The board was not found. Check the board token.',
    http_status: 404,
  },
})
const never = source({
  source_configuration_id: 3,
  display_name: 'Globex',
  company_name: 'Globex',
  external_identifier: 'globex',
  open_postings: 0,
  last_result: null,
})
const disabled = source({
  source_configuration_id: 4,
  display_name: 'Initech',
  company_name: 'Initech',
  external_identifier: 'initech',
  enabled: false,
  version: 3,
  last_result: null,
})

const schedule = {
  run_times_local: ['07:30'],
  timezone: 'Europe/Lisbon',
  enabled: false,
  company_recency_days: 30,
  set_aside_below_fit: 20,
  version: 1,
  next_run_at: null,
  next_run_local: null,
}

let sources: unknown[]
let runs: unknown[]

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

function row(name: string) {
  return screen.getByRole('row', { name: new RegExp(name) })
}

describe('Sources screen', () => {
  beforeEach(() => {
    get.mockReset()
    post.mockReset()
    put.mockReset()
    sources = [source(), failed, never, disabled]
    runs = []
    get.mockImplementation((path: string) => {
      if (path === '/api/v1/sources') return Promise.resolve({ data: { items: sources } })
      if (path === '/api/v1/collection-runs')
        return Promise.resolve({ data: { items: runs, next_before_collection_run_id: null } })
      if (path === '/api/v1/settings/schedule') return Promise.resolve({ data: schedule })
      if (path === '/api/v1/source-catalogue') return Promise.resolve({ data: { items: [] } })
      if (path === '/api/v1/source-scope')
        return Promise.resolve({
          data: {
            configured: true,
            country_codes: ['PT'],
            include_worldwide: true,
            any_country: false,
            onsite_areas: [],
          },
        })
      return Promise.reject(new Error(`unexpected GET ${path}`))
    })
  })

  it('lists each board with company, postings, counts and a status in words', async () => {
    renderSources()
    const acme = await screen.findByRole('row', { name: /Acme Robotics/ })
    expect(within(acme).getByText('Succeeded')).toBeInTheDocument()
    expect(within(acme).getByText('41')).toBeInTheDocument() // postings
    expect(within(acme).getByText('5')).toBeInTheDocument() // new
    expect(within(acme).getByText('2')).toBeInTheDocument() // changed
    expect(acme.querySelector('time')).toHaveAttribute('datetime', '2026-10-08T07:30:05Z')
  })

  it('shows the classified reason when a source failed', async () => {
    renderSources()
    await screen.findByText('Contoso')
    const contoso = row('Contoso')
    expect(within(contoso).getByText('Failed')).toBeInTheDocument()
    expect(within(contoso).getByText(/board was not found/i)).toBeInTheDocument()
    expect(within(contoso).getByText(/not_found/)).toBeInTheDocument()
  })

  it('says so when a board never ran or is disabled', async () => {
    renderSources()
    await screen.findByText('Globex')
    expect(within(row('Globex')).getByText('Never run')).toBeInTheDocument()
    expect(within(row('Initech')).getByText('Disabled')).toBeInTheDocument()
  })

  it('shows the schedule and saves a change with the version the owner saw', async () => {
    const user = userEvent.setup()
    renderSources()
    const card = (await screen.findByRole('heading', { name: 'Daily schedule' })).closest(
      'section',
    )!
    expect(await within(card).findByLabelText('Run time 1')).toHaveValue('07:30')
    expect(within(card).getByLabelText('Time zone')).toHaveValue('Europe/Lisbon')
    expect(within(card).getByLabelText('Run every day')).not.toBeChecked()
    expect(within(card).getByText(/scheduled runs are off/i)).toBeInTheDocument()
    expect(within(card).getByRole('button', { name: 'Save schedule' })).toBeDisabled()

    await user.click(within(card).getByLabelText('Run every day'))
    put.mockResolvedValue({
      data: {
        ...schedule,
        enabled: true,
        version: 2,
        next_run_local: '2026-10-09 07:30',
        next_run_at: '2026-10-09T06:30:00Z',
      },
    })
    await user.click(within(card).getByRole('button', { name: 'Save schedule' }))
    expect(put).toHaveBeenCalledWith('/api/v1/settings/schedule', {
      body: {
        run_times_local: ['07:30'],
        timezone: 'Europe/Lisbon',
        enabled: true,
        company_recency_days: 30,
        set_aside_below_fit: 20,
        expected_version: 1,
      },
    })
    expect(await within(card).findByText(/2026-10-09 07:30/)).toBeInTheDocument()
  })

  it('changes the fit below which the inbox sets recommended jobs aside', async () => {
    const user = userEvent.setup()
    renderSources()
    const card = (await screen.findByRole('heading', { name: 'Daily schedule' })).closest(
      'section',
    )!
    const floor = await within(card).findByLabelText(/set aside recommended jobs with a fit below/i)
    expect(floor).toHaveValue(20)
    await user.clear(floor)
    await user.type(floor, '101')
    expect(within(card).getByText(/whole number from 0 to 100/i)).toBeInTheDocument()
    expect(within(card).getByRole('button', { name: 'Save schedule' })).toBeDisabled()
    await user.clear(floor)
    await user.type(floor, '0')
    put.mockResolvedValue({ data: { ...schedule, set_aside_below_fit: 0, version: 2 } })
    await user.click(within(card).getByRole('button', { name: 'Save schedule' }))
    expect(put).toHaveBeenCalledWith('/api/v1/settings/schedule', {
      body: expect.objectContaining({ set_aside_below_fit: 0, expected_version: 1 }),
    })
  })

  it('changes how many days of offers the company views count', async () => {
    const user = userEvent.setup()
    renderSources()
    const card = (await screen.findByRole('heading', { name: 'Daily schedule' })).closest(
      'section',
    )!
    const days = await within(card).findByLabelText(/offers first seen in the last/i)
    expect(days).toHaveValue(30)
    await user.clear(days)
    await user.type(days, '0')
    expect(within(card).getByText(/whole number from 1 to 365/i)).toBeInTheDocument()
    expect(within(card).getByRole('button', { name: 'Save schedule' })).toBeDisabled()
    await user.clear(days)
    await user.type(days, '14')
    put.mockResolvedValue({ data: { ...schedule, company_recency_days: 14, version: 2 } })
    await user.click(within(card).getByRole('button', { name: 'Save schedule' }))
    expect(put).toHaveBeenCalledWith('/api/v1/settings/schedule', {
      body: expect.objectContaining({ company_recency_days: 14, expected_version: 1 }),
    })
  })

  it('adds and removes run times and saves them sorted', async () => {
    const user = userEvent.setup()
    renderSources()
    const card = (await screen.findByRole('heading', { name: 'Daily schedule' })).closest(
      'section',
    )!
    expect(await within(card).findByLabelText('Run time 1')).toHaveValue('07:30')
    // the only time cannot be removed: turn the schedule off instead
    expect(within(card).getByRole('button', { name: 'Remove run time 1' })).toBeDisabled()

    await user.click(within(card).getByRole('button', { name: 'Add a run time' }))
    await user.click(within(card).getByRole('button', { name: 'Add a run time' }))
    expect(within(card).getByLabelText('Run time 3')).toBeInTheDocument()
    fireEvent.change(within(card).getByLabelText('Run time 1'), { target: { value: '16:00' } })
    fireEvent.change(within(card).getByLabelText('Run time 2'), { target: { value: '09:00' } })
    fireEvent.change(within(card).getByLabelText('Run time 3'), { target: { value: '12:00' } })
    await user.click(within(card).getByRole('button', { name: 'Remove run time 2' }))
    expect(within(card).queryByLabelText('Run time 3')).not.toBeInTheDocument()
    await user.click(within(card).getByRole('button', { name: 'Add a run time' }))
    fireEvent.change(within(card).getByLabelText('Run time 3'), { target: { value: '09:00' } })

    put.mockResolvedValue({
      data: { ...schedule, run_times_local: ['09:00', '12:00', '16:00'], version: 2 },
    })
    await user.click(within(card).getByRole('button', { name: 'Save schedule' }))
    expect(put).toHaveBeenCalledWith('/api/v1/settings/schedule', {
      body: expect.objectContaining({
        run_times_local: ['09:00', '12:00', '16:00'],
        expected_version: 1,
      }),
    })
  })

  it('refuses a repeated or empty run time', async () => {
    const user = userEvent.setup()
    renderSources()
    const card = (await screen.findByRole('heading', { name: 'Daily schedule' })).closest(
      'section',
    )!
    await within(card).findByLabelText('Run time 1')
    await user.click(within(card).getByRole('button', { name: 'Add a run time' }))
    fireEvent.change(within(card).getByLabelText('Run time 2'), { target: { value: '07:30' } })
    expect(within(card).getByText(/each run time only once/i)).toBeInTheDocument()
    expect(within(card).getByRole('button', { name: 'Save schedule' })).toBeDisabled()
    fireEvent.change(within(card).getByLabelText('Run time 2'), { target: { value: '' } })
    expect(within(card).getByText(/fill in every run time/i)).toBeInTheDocument()
    expect(within(card).getByRole('button', { name: 'Save schedule' })).toBeDisabled()
  })

  it('reports a rejected schedule', async () => {
    const user = userEvent.setup()
    renderSources()
    const card = (await screen.findByRole('heading', { name: 'Daily schedule' })).closest(
      'section',
    )!
    await user.clear(await within(card).findByLabelText('Time zone'))
    await user.type(within(card).getByLabelText('Time zone'), 'Mars/Phobos')
    put.mockResolvedValue(envelope('Unknown time zone: Mars/Phobos.'))
    await user.click(within(card).getByRole('button', { name: 'Save schedule' }))
    expect(await within(card).findByRole('alert')).toHaveTextContent(/unknown time zone/i)
  })

  it('lists the recent runs with their trigger and outcome', async () => {
    runs = [
      {
        collection_run_id: 9,
        source_configuration_id: null,
        trigger: 'scheduled',
        status: 'partial',
        requested_at: '2026-10-08T07:30:00Z',
        started_at: '2026-10-08T07:30:01Z',
        finished_at: '2026-10-08T07:31:00Z',
        error_class: null,
        results: [result, result],
      },
      {
        collection_run_id: 8,
        source_configuration_id: 1,
        trigger: 'manual',
        status: 'failed',
        requested_at: '2026-10-07T07:30:00Z',
        started_at: null,
        finished_at: '2026-10-07T07:31:00Z',
        error_class: 'interrupted',
        results: [],
      },
    ]
    renderSources()
    const history = (await screen.findByRole('heading', { name: 'Recent runs' })).closest(
      'section',
    )!
    const first = within(history).getByRole('row', { name: /Scheduled/ })
    expect(within(first).getByText('Partly succeeded')).toBeInTheDocument()
    const second = within(history).getByRole('row', { name: /Manual/ })
    expect(within(second).getByText('Failed')).toBeInTheDocument()
    expect(within(second).getByText(/interrupted/)).toBeInTheDocument()
  })

  it('guides the owner when no board is configured', async () => {
    sources = []
    renderSources()
    expect(await screen.findByText(/no boards yet/i)).toBeInTheDocument()
  })

  it('reports a failed load and lets the owner retry', async () => {
    const load = get.getMockImplementation()!
    let failedOnce = false
    get.mockImplementation((path: string) => {
      if (path === '/api/v1/sources' && !failedOnce) {
        failedOnce = true
        return Promise.reject(new Error('network'))
      }
      return load(path)
    })
    renderSources()
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not load/i)
    await userEvent.click(screen.getByRole('button', { name: /try again/i }))
    expect(await screen.findByText('Acme Robotics')).toBeInTheDocument()
  })

  describe('adding a board', () => {
    it('cannot be submitted empty', async () => {
      renderSources()
      await screen.findByText('Acme Robotics')
      expect(screen.getByRole('button', { name: /validate & add/i })).toBeDisabled()
    })

    it('validates and adds, then refreshes the list', async () => {
      post.mockResolvedValue({
        data: source({ display_name: 'New Co' }),
        response: { status: 201 },
      })
      renderSources()
      await screen.findByText('Acme Robotics')
      await userEvent.type(screen.getByLabelText(/board token/i), '  newco ')
      await userEvent.click(screen.getByRole('button', { name: /validate & add/i }))

      expect(post).toHaveBeenCalledWith('/api/v1/sources', {
        body: { source_type: 'greenhouse', external_identifier: 'newco', enabled: true },
      })
      expect(await screen.findByRole('status')).toHaveTextContent(/added new co/i)
      expect(screen.getByLabelText(/board token/i)).toHaveValue('')
      expect(get.mock.calls.filter(([p]) => p === '/api/v1/sources').length).toBeGreaterThan(1)
    })

    it('shows why a board was refused and keeps what was typed', async () => {
      post.mockResolvedValue(
        envelope('The board was not found. Check the board token.', 'not_found'),
      )
      renderSources()
      await screen.findByText('Acme Robotics')
      await userEvent.type(screen.getByLabelText(/board token/i), 'nope')
      await userEvent.click(screen.getByRole('button', { name: /validate & add/i }))
      const alert = await screen.findByRole('alert')
      expect(alert).toHaveTextContent(/board was not found/i)
      expect(screen.getByLabelText(/board token/i)).toHaveValue('nope')
    })

    it('adds a Lever board with the company name the owner typed', async () => {
      post.mockResolvedValue({
        data: source({ display_name: 'Real Co' }),
        response: { status: 201 },
      })
      renderSources()
      await screen.findByText('Acme Robotics')
      await userEvent.selectOptions(screen.getByLabelText(/board type/i), 'lever')
      await userEvent.type(screen.getByLabelText(/company identifier/i), 'real-co')
      await userEvent.type(screen.getByLabelText(/company name/i), 'Real Co')
      await userEvent.click(screen.getByRole('button', { name: /validate & add/i }))
      expect(post).toHaveBeenCalledWith('/api/v1/sources', {
        body: {
          source_type: 'lever',
          external_identifier: 'real-co',
          enabled: true,
          display_name: 'Real Co',
        },
      })
    })

    it('does not ask for a company name when the board publishes one', async () => {
      renderSources()
      await screen.findByText('Acme Robotics')
      expect(screen.queryByLabelText(/company name/i)).not.toBeInTheDocument()
      await userEvent.selectOptions(screen.getByLabelText(/board type/i), 'smartrecruiters')
      expect(screen.queryByLabelText(/company name/i)).not.toBeInTheDocument()
      expect(screen.getByLabelText(/company identifier/i)).toBeInTheDocument()
    })

    it('adds an Eightfold careers site by its address', async () => {
      post.mockResolvedValue({ data: source(), response: { status: 201 } })
      renderSources()
      await screen.findByText('Acme Robotics')
      await userEvent.selectOptions(screen.getByLabelText(/board type/i), 'eightfold')
      expect(screen.queryByLabelText(/company name/i)).not.toBeInTheDocument()
      await userEvent.type(screen.getByLabelText(/careers site address/i), ' jobs.synthco.example ')
      await userEvent.click(screen.getByRole('button', { name: /validate & add/i }))
      expect(post).toHaveBeenCalledWith('/api/v1/sources', {
        body: {
          source_type: 'eightfold',
          external_identifier: 'jobs.synthco.example',
          enabled: true,
        },
      })
    })

    it('sends no company name when it was left empty', async () => {
      post.mockResolvedValue({ data: source(), response: { status: 201 } })
      renderSources()
      await screen.findByText('Acme Robotics')
      await userEvent.selectOptions(screen.getByLabelText(/board type/i), 'ashby')
      await userEvent.type(screen.getByLabelText(/company identifier/i), 'some-co')
      await userEvent.click(screen.getByRole('button', { name: /validate & add/i }))
      expect(post).toHaveBeenCalledWith('/api/v1/sources', {
        body: { source_type: 'ashby', external_identifier: 'some-co', enabled: true },
      })
    })

    it('explains an unreachable server', async () => {
      post.mockRejectedValue(new Error('network'))
      renderSources()
      await screen.findByText('Acme Robotics')
      await userEvent.type(screen.getByLabelText(/board token/i), 'x')
      await userEvent.click(screen.getByRole('button', { name: /validate & add/i }))
      expect(await screen.findByRole('alert')).toHaveTextContent(/could not reach/i)
    })
  })

  describe('running', () => {
    it('queues a run of one board', async () => {
      post.mockResolvedValue({
        data: { collection_run_id: 9, status: 'queued' },
        response: { status: 202 },
      })
      renderSources()
      await screen.findByText('Acme Robotics')
      await userEvent.click(screen.getByRole('button', { name: 'Run Acme Robotics now' }))
      expect(post).toHaveBeenCalledWith('/api/v1/sources/{source_configuration_id}/run', {
        params: { path: { source_configuration_id: 1 } },
      })
    })

    it('queues a run of every enabled board', async () => {
      post.mockResolvedValue({
        data: { collection_run_id: 9, status: 'queued' },
        response: { status: 202 },
      })
      renderSources()
      await screen.findByText('Acme Robotics')
      await userEvent.click(screen.getByRole('button', { name: /run all now/i }))
      expect(post).toHaveBeenCalledWith('/api/v1/collection-runs')
    })

    it('shows the API reason when a run cannot start', async () => {
      post.mockResolvedValue(
        envelope('There is no enabled source to collect. Enable or add a source first.'),
      )
      renderSources()
      await screen.findByText('Acme Robotics')
      await userEvent.click(screen.getByRole('button', { name: /run all now/i }))
      expect(await screen.findByRole('alert')).toHaveTextContent(/no enabled source/i)
    })

    it('marks boards as running and blocks new runs while one is in progress', async () => {
      runs = [
        {
          collection_run_id: 9,
          source_configuration_id: null,
          trigger: 'manual',
          status: 'running',
          requested_at: '2026-10-08T08:00:00Z',
          started_at: '2026-10-08T08:00:01Z',
          finished_at: null,
          error_class: null,
          results: [],
        },
      ]
      renderSources()
      await screen.findByText('Acme Robotics')
      expect(await within(row('Acme Robotics')).findByText('Running')).toBeInTheDocument()
      expect(within(row('Initech')).queryByText('Running')).not.toBeInTheDocument() // disabled: not part of an all-run
      expect(screen.getByRole('button', { name: /run all now/i })).toBeDisabled()
      expect(screen.getByRole('button', { name: 'Run Acme Robotics now' })).toBeDisabled()
    })
  })

  describe('enabling and disabling', () => {
    it('enables a board using the version the owner saw', async () => {
      put.mockResolvedValue({
        data: source({ enabled: true, version: 4 }),
        response: { status: 200 },
      })
      renderSources()
      await screen.findByText('Initech')
      await userEvent.click(screen.getByRole('button', { name: 'Enable Initech' }))
      expect(put).toHaveBeenCalledWith('/api/v1/sources/{source_configuration_id}', {
        params: { path: { source_configuration_id: 4 } },
        body: { expected_version: 3, enabled: true },
      })
    })

    it('disables an enabled board', async () => {
      put.mockResolvedValue({
        data: source({ enabled: false, version: 2 }),
        response: { status: 200 },
      })
      renderSources()
      await screen.findByText('Acme Robotics')
      await userEvent.click(screen.getByRole('button', { name: 'Disable Acme Robotics' }))
      expect(put).toHaveBeenCalledWith('/api/v1/sources/{source_configuration_id}', {
        params: { path: { source_configuration_id: 1 } },
        body: { expected_version: 1, enabled: false },
      })
    })

    it('tells the owner to reload after a version conflict', async () => {
      put.mockResolvedValue(envelope('The source changed since it was loaded.'))
      renderSources()
      await screen.findByText('Acme Robotics')
      await userEvent.click(screen.getByRole('button', { name: 'Disable Acme Robotics' }))
      expect(await screen.findByRole('alert')).toHaveTextContent(/changed since it was loaded/i)
    })
  })
})
