import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { TAXONOMY, makeIntent, makeProfile } from '@/test/builders'
import { ProfileIntent } from './ProfileIntent'

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

let profiles: unknown[]
let intents: Record<number, unknown[]>

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ProfileIntent />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('Profile & intent screen', () => {
  beforeEach(() => {
    get.mockReset()
    post.mockReset()
    put.mockReset()
    profiles = [makeProfile()]
    intents = { 1: [makeIntent()], 2: [] }
    get.mockImplementation(
      (path: string, options?: { params?: { path?: Record<string, number> } }) => {
        switch (path) {
          case '/api/v1/profiles':
            return Promise.resolve({ data: { items: profiles } })
          case '/api/v1/taxonomy':
            return Promise.resolve({ data: TAXONOMY })
          case '/api/v1/profiles/{career_profile_id}/intents':
            return Promise.resolve({
              data: { items: intents[options?.params?.path?.career_profile_id ?? 0] ?? [] },
            })
          case '/api/v1/profiles/{career_profile_id}/revisions':
          case '/api/v1/intents/{search_intent_id}/revisions':
            return Promise.resolve({ data: { items: [] } })
          case '/api/v1/settings/schedule':
            return Promise.resolve({
              data: {
                run_times_local: ['07:30'],
                timezone: 'Europe/Lisbon',
                enabled: true,
                company_recency_days: 30,
                set_aside_below_fit: 30,
                version: 4,
                next_run_at: null,
                next_run_local: null,
              },
            })
          case '/api/v1/settings/ai':
            return Promise.resolve({
              data: {
                mode: 'no_ai',
                import_connection_id: null,
                jobs_connection_id: null,
                key_configured: true,
                connections: [],
                privacy: { redact_contact_details: true, version: 1 },
              },
            })
          default:
            return Promise.reject(new Error(`unexpected GET ${path}`))
        }
      },
    )
  })

  afterEach(() => vi.restoreAllMocks())

  it('guides the owner to create the first profile', async () => {
    profiles = []
    post.mockResolvedValue({ data: makeProfile({}, 0), response: { status: 201 } })
    renderPage()
    expect(await screen.findByText(/create your first profile/i)).toBeInTheDocument()
    await userEvent.clear(screen.getByLabelText('Profile name'))
    await userEvent.type(screen.getByLabelText('Profile name'), 'AI Solutions')
    await userEvent.click(screen.getByRole('button', { name: /create profile/i }))
    expect(post).toHaveBeenCalledWith('/api/v1/profiles', {
      body: { title: 'AI Solutions', visibility: 'private' },
    })
  })

  it('shows the selected profile and intent with their revisions and five tabs', async () => {
    renderPage()
    expect(await screen.findByLabelText('Career profile')).toHaveDisplayValue(
      'AI Solutions · revision 1',
    )
    expect(await screen.findByLabelText('Search intent')).toHaveDisplayValue(
      'My search · revision 1',
    )
    const tabs = screen.getByRole('tablist', { name: /profile and intent sections/i })
    expect(
      within(tabs)
        .getAllByRole('tab')
        .map((t) => t.textContent),
    ).toEqual(['Profile', 'Import CV', 'Search intent', 'Scoring weights', 'History'])
    expect(within(tabs).getByRole('tab', { name: 'Profile' })).toHaveAttribute(
      'aria-selected',
      'true',
    )
    expect(screen.getByLabelText('Headline')).toHaveValue('AI solutions engineer')
  })

  it('switches between the sections', async () => {
    renderPage()
    await screen.findByLabelText('Headline')
    await userEvent.click(screen.getByRole('tab', { name: 'Search intent' }))
    expect(await screen.findByLabelText('Intent name')).toBeVisible()
    await userEvent.click(screen.getByRole('tab', { name: 'Scoring weights' }))
    expect(await screen.findByRole('slider', { name: 'Compensation weight' })).toBeVisible()
    await userEvent.click(screen.getByRole('tab', { name: 'History' }))
    expect(await screen.findByText(/nothing is overwritten/i)).toBeVisible()
  })

  it('sets the fit below which recommended jobs are set aside from the weights section', async () => {
    put.mockResolvedValue({ data: {} })
    renderPage()
    await screen.findByLabelText('Headline')
    await userEvent.click(screen.getByRole('tab', { name: 'Scoring weights' }))
    const slider = await screen.findByRole('slider', { name: 'Set aside below fit' })
    expect(slider).toHaveValue('30')
    const save = screen.getByRole('button', { name: 'Save limit' })
    expect(save).toBeDisabled()
    fireEvent.change(slider, { target: { value: '45' } })
    expect(screen.getByText('Below 45')).toBeVisible()
    await userEvent.click(save)
    expect(put).toHaveBeenCalledWith('/api/v1/settings/schedule', {
      body: {
        run_times_local: ['07:30'],
        timezone: 'Europe/Lisbon',
        enabled: true,
        company_recency_days: 30,
        set_aside_below_fit: 45,
        expected_version: 4,
      },
    })
  })

  it('offers to create an intent when the profile has none, starting from sensible defaults', async () => {
    intents = { 1: [] }
    post.mockResolvedValue({ data: makeIntent(), response: { status: 201 } })
    renderPage()
    await screen.findByLabelText('Headline')
    await userEvent.click(screen.getByRole('tab', { name: 'Search intent' }))
    expect(await screen.findByText(/no search intent yet/i)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /create search intent/i }))
    const [path, options] = post.mock.calls[0]
    expect(path).toBe('/api/v1/profiles/{career_profile_id}/intents')
    expect(options.params).toEqual({ path: { career_profile_id: 1 } })
    expect(options.body.enabled).toBe(true)
    expect(options.body.stances.work_arrangements).toHaveLength(3)
    expect(options.body.work_rules.onsite_hybrid.base_place).toBe('Lisbon, Portugal')
  })

  it('does not offer an intent for a profile that has no revision yet', async () => {
    profiles = [makeProfile({}, 0)]
    intents = { 1: [] }
    renderPage()
    await screen.findByLabelText('Headline')
    expect(screen.getByRole('button', { name: /new intent/i })).toBeDisabled()
    await userEvent.click(screen.getByRole('tab', { name: 'Search intent' }))
    expect(await screen.findByText(/save the profile first/i)).toBeInTheDocument()
  })

  it('creates another profile with a name', async () => {
    post.mockResolvedValue({
      data: makeProfile({ career_profile_id: 2, title: 'Data Engineering' }, 0),
      response: { status: 201 },
    })
    renderPage()
    await screen.findByLabelText('Headline')
    await userEvent.click(screen.getByRole('button', { name: /new profile/i }))
    await userEvent.type(screen.getByLabelText('Profile name'), 'Data Engineering')
    await userEvent.click(screen.getByRole('button', { name: /create profile/i }))
    expect(post).toHaveBeenCalledWith('/api/v1/profiles', {
      body: { title: 'Data Engineering', visibility: 'private' },
    })
  })

  it('asks before switching profile while there are unsaved changes', async () => {
    profiles = [makeProfile(), makeProfile({ career_profile_id: 2, title: 'Data Engineering' })]
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    renderPage()
    const headline = await screen.findByLabelText('Headline')
    await userEvent.type(headline, '!')
    await userEvent.selectOptions(screen.getByLabelText('Career profile'), '2')
    expect(confirm).toHaveBeenCalled()
    expect(screen.getByLabelText('Career profile')).toHaveDisplayValue('AI Solutions · revision 1')
    expect(screen.getByLabelText('Headline')).toHaveValue('AI solutions engineer!')

    confirm.mockReturnValue(true)
    await userEvent.selectOptions(screen.getByLabelText('Career profile'), '2')
    expect(screen.getByLabelText('Career profile')).toHaveDisplayValue(
      'Data Engineering · revision 1',
    )
  })

  it('reports a load failure and lets the owner retry', async () => {
    const load = get.getMockImplementation()!
    let failed = false
    get.mockImplementation((path: string, options?: unknown) => {
      if (path === '/api/v1/profiles' && !failed) {
        failed = true
        return Promise.reject(new Error('network'))
      }
      return load(path, options as never)
    })
    renderPage()
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not load/i)
    await userEvent.click(screen.getByRole('button', { name: /try again/i }))
    expect(await screen.findByLabelText('Headline')).toBeInTheDocument()
  })
})
