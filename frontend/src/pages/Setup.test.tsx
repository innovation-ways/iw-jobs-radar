import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { TAXONOMY, makeProfile } from '@/test/builders'
import { Setup } from './Setup'

const get = vi.fn()
const post = vi.fn()
const put = vi.fn()
vi.mock('@/api/client', () => ({
  api: {
    GET: (...a: unknown[]) => get(...a),
    POST: (...a: unknown[]) => post(...a),
    PUT: (...a: unknown[]) => put(...a),
  },
}))
vi.mock('@/features/profile/queries', async (original) => ({
  ...(await original<typeof import('@/features/profile/queries')>()),
  searchPlaces: vi.fn().mockResolvedValue([
    {
      label: 'Porto, Portugal',
      city: 'Porto',
      country: 'PT',
      latitude: 41.1485,
      longitude: -8.61097,
      timezone: 'Europe/Lisbon',
      population: 252687,
    },
  ]),
}))

const trades = {
  key: 'construction_trades',
  name: 'Construction and skilled trades',
  description: 'Electricians, plumbers and site roles.',
  version: 1,
  role_family_count: 16,
  sector_count: 5,
  active: false,
}

let packs: (typeof trades)[]

function renderSetup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/setup']}>
        <Routes>
          <Route path="/setup" element={<Setup />} />
          <Route path="/profile" element={<p>profile page</p>} />
          <Route path="/inbox" element={<p>inbox page</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('Setup', () => {
  beforeEach(() => {
    for (const m of [get, post, put]) m.mockReset()
    window.localStorage.clear()
    packs = [trades]
    get.mockImplementation((path: string) => {
      if (path === '/api/v1/packs')
        return Promise.resolve({
          data: { packs, active_count: packs.filter((p) => p.active).length },
        })
      if (path === '/api/v1/taxonomy') return Promise.resolve({ data: TAXONOMY })
      if (path === '/api/v1/setup/intent-defaults')
        return Promise.resolve({
          data: {
            pack_key: 'construction_trades',
            work_arrangements: { onsite: 'preferred', remote: 'rejected' },
            schedules: { day: 'preferred' },
            travel_levels: {},
            weights: { role_responsibilities: 25, qualifications: 12, schedule_travel: 8 },
            reject_missing_credentials: true,
          },
        })
      if (path === '/api/v1/locations/search') return Promise.resolve({ data: { items: [] } })
      return Promise.reject(new Error(`unexpected GET ${path}`))
    })
    put.mockImplementation((path: string) => {
      if (path === '/api/v1/packs/{pack_key}') {
        packs = packs.map((p) => ({ ...p, active: true }))
        return Promise.resolve({ data: packs[0] })
      }
      return Promise.resolve({ data: { created: true, profile: makeProfile() } })
    })
    post.mockImplementation((path: string) =>
      path === '/api/v1/profiles'
        ? Promise.resolve({ data: makeProfile() })
        : Promise.resolve({ data: { search_intent_id: 9 } }),
    )
  })

  async function chooseTheTrades(user: ReturnType<typeof userEvent.setup>) {
    const card = (
      await screen.findByRole('heading', { name: 'Construction and skilled trades' })
    ).closest('section')!
    await user.click(within(card).getByRole('button', { name: 'Switch on' }))
    await user.click(await screen.findByRole('button', { name: 'Continue' }))
  }

  it('starts by asking for the fields of work and keeps Continue off until one is chosen', async () => {
    renderSetup()
    expect(await screen.findByRole('heading', { name: /fields of work/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Continue' })).toBeDisabled()
    expect(screen.getByRole('button', { name: /start from scratch/i })).toBeEnabled()
  })

  it('asks about the person next and checks it before going on', async () => {
    const user = userEvent.setup()
    renderSetup()
    await chooseTheTrades(user)
    expect(await screen.findByRole('heading', { name: /about you/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Continue' })).toBeDisabled()
    await user.type(screen.getByLabelText('Headline'), 'Electrician')
    await user.type(screen.getByRole('combobox', { name: 'Base place' }), 'Porto')
    await user.click(await screen.findByRole('option', { name: /Porto, Portugal/ }))
    expect(screen.getByRole('button', { name: 'Continue' })).toBeEnabled()
  })

  it('creates the profile with its licences and a first search made from the pack’s suggestions', async () => {
    const user = userEvent.setup()
    renderSetup()
    await chooseTheTrades(user)
    await user.type(await screen.findByLabelText('Headline'), 'Electrician')
    await user.type(screen.getByRole('combobox', { name: 'Base place' }), 'Porto')
    await user.click(await screen.findByRole('option', { name: /Porto, Portugal/ }))
    await user.clear(screen.getByLabelText('Years of experience'))
    await user.type(screen.getByLabelText('Years of experience'), '8')
    await user.type(screen.getByLabelText('Licences and certifications'), 'Gas Safe registration,')
    await user.click(screen.getByRole('button', { name: 'Continue' }))

    expect(await screen.findByRole('heading', { name: /first search/i })).toBeInTheDocument()
    expect(screen.getByText(/on-site work is preferred/i)).toBeInTheDocument()
    expect(screen.getByText(/remote work is ruled out/i)).toBeInTheDocument()
    expect(
      screen.getByText(/needs a licence or certification you do not hold/i),
    ).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /create my profile and search/i }))
    expect(await screen.findByText('profile page')).toBeInTheDocument()

    const profileSave = put.mock.calls.find((c) => c[0] === '/api/v1/profiles/{career_profile_id}')!
    expect(profileSave[1].body).toMatchObject({
      headline: 'Electrician',
      years_experience: 8,
      expected_current_revision: null,
      base_location: { place: 'Porto, Portugal', country: 'PT', timezone: 'Europe/Lisbon' },
    })
    expect(profileSave[1].body.skills).toEqual([
      { name: 'Gas Safe registration', kind: 'credential', level: 'expert', years: 0 },
    ])
    const intent = post.mock.calls.find(
      (c) => c[0] === '/api/v1/profiles/{career_profile_id}/intents',
    )!
    const body = intent[1].body
    expect(body.enabled).toBe(true)
    expect(body.filters.reject_missing_credentials).toBe(true)
    expect(body.weights.qualifications).toBe(12)
    expect(body.stances.work_arrangements).toContainEqual({ key: 'onsite', stance: 'preferred' })
    expect(body.stances.work_arrangements).toContainEqual({ key: 'remote', stance: 'rejected' })
  })

  it('lets the owner go on without a pack and skip the whole setup', async () => {
    const user = userEvent.setup()
    renderSetup()
    await user.click(await screen.findByRole('button', { name: /start from scratch/i }))
    expect(await screen.findByRole('heading', { name: /about you/i })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /skip the setup/i }))
    expect(await screen.findByText('inbox page')).toBeInTheDocument()
    expect(window.localStorage.getItem('jobs-radar-setup-skipped')).toBe('1')
  })

  it('shows why creating failed and creates nothing twice', async () => {
    const user = userEvent.setup()
    post.mockImplementation(() =>
      Promise.resolve({ error: { error: { code: 'x', message: 'The title is taken.' } } }),
    )
    renderSetup()
    await chooseTheTrades(user)
    await user.type(await screen.findByLabelText('Headline'), 'Electrician')
    await user.type(screen.getByRole('combobox', { name: 'Base place' }), 'Porto')
    await user.click(await screen.findByRole('option', { name: /Porto, Portugal/ }))
    await user.click(screen.getByRole('button', { name: 'Continue' }))
    await user.click(await screen.findByRole('button', { name: /create my profile and search/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/title is taken/i)
  })
})
