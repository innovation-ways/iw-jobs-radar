import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { makeProfile } from '@/test/builders'
import { ProfilePanel } from './ProfilePanel'

const put = vi.fn()
const get = vi.fn()
const del = vi.fn()
const download = vi.fn()
vi.mock('@/api/client', () => ({
  api: {
    PUT: (...args: unknown[]) => put(...args),
    GET: (...args: unknown[]) => get(...args),
    DELETE: (...args: unknown[]) => del(...args),
  },
}))
vi.mock('@/lib/download', () => ({ downloadJson: (...args: unknown[]) => download(...args) }))
vi.mock('./queries', async (original) => ({
  ...(await original<typeof import('./queries')>()),
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

function renderPanel(profile = makeProfile()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ProfilePanel profile={profile} />
    </QueryClientProvider>,
  )
}

const saved = (profile = makeProfile()) => ({
  data: { created: true, profile },
  response: { status: 200 },
})

describe('ProfilePanel', () => {
  beforeEach(() => {
    put.mockReset()
    get.mockReset()
    del.mockReset()
    download.mockReset()
  })

  it('shows the summary, skills, experience and revision', () => {
    renderPanel()
    expect(screen.getByLabelText('Headline')).toHaveValue('AI solutions engineer')
    expect(screen.getByRole('combobox', { name: 'Base place' })).toHaveValue('Lisbon, Portugal')
    expect(screen.getByLabelText('Years of experience')).toHaveValue('12')
    expect(
      screen.getAllByLabelText('Skill name').map((i) => (i as HTMLInputElement).value),
    ).toEqual(['Python', 'Kubernetes'])
    expect(screen.getByLabelText('Role title')).toHaveValue('Solutions Architect')
    expect(screen.getByText(/revision 1/i)).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: /unsaved/i })).not.toBeInTheDocument()
  })

  it('saves edits as the next revision, sending provenance-free facts', async () => {
    put.mockResolvedValue(saved())
    renderPanel()
    const headline = screen.getByLabelText('Headline')
    await userEvent.clear(headline)
    await userEvent.type(headline, 'Principal AI engineer')
    await userEvent.click(screen.getByRole('button', { name: /save revision/i }))

    const [path, options] = put.mock.calls[0]
    expect(path).toBe('/api/v1/profiles/{career_profile_id}')
    expect(options.params).toEqual({ path: { career_profile_id: 1 } })
    expect(options.body.expected_current_revision).toBe(1)
    expect(options.body.headline).toBe('Principal AI engineer')
    expect(options.body.skills[0]).toEqual({
      name: 'Python',
      kind: 'technology',
      level: 'expert',
      years: 10,
    })
    expect(JSON.stringify(options.body)).not.toContain('provenance')
  })

  it('shows the career directions right after the summary, before the skills', () => {
    renderPanel()
    const titles = screen
      .getAllByRole('heading', { level: 2 })
      .map((heading) => heading.textContent)
    const order = ['Summary', 'Career directions', 'Skills', 'Experience']
    expect(titles.filter((title) => order.includes(title ?? ''))).toEqual(order)
  })

  it('saves a career direction typed by the owner with the profile', async () => {
    put.mockResolvedValue(saved())
    renderPanel()
    await userEvent.click(screen.getByRole('button', { name: /add a direction/i }))
    await userEvent.type(screen.getByLabelText(/direction label/i), 'Billing SME')
    await userEvent.type(screen.getByLabelText(/direction text/i), 'Telecom billing roles.')
    await userEvent.click(screen.getByRole('button', { name: /save revision/i }))
    expect(put.mock.calls[0][1].body.directions).toEqual([
      { label: 'Billing SME', text: 'Telecom billing roles.', enabled: true },
    ])
  })

  it('does not save a direction without text and says why', async () => {
    renderPanel()
    await userEvent.click(screen.getByRole('button', { name: /add a direction/i }))
    await userEvent.type(screen.getByLabelText(/direction label/i), 'Billing SME')
    expect(screen.getByRole('button', { name: /save revision/i })).toBeDisabled()
    expect(screen.getByText(/text of what you are looking for/i)).toBeInTheDocument()
  })

  it('adds, edits and removes skills', async () => {
    put.mockResolvedValue(saved())
    renderPanel()
    await userEvent.click(screen.getByRole('button', { name: /add skill/i }))
    const names = screen.getAllByLabelText('Skill name')
    await userEvent.type(names[2], 'Rust')
    const rustRow = names[2].closest('tr')!
    await userEvent.selectOptions(within(rustRow).getByLabelText('Skill level'), 'advanced')
    await userEvent.clear(within(rustRow).getByLabelText('Skill years'))
    await userEvent.type(within(rustRow).getByLabelText('Skill years'), '3')
    await userEvent.click(screen.getByRole('button', { name: 'Remove Kubernetes' }))
    await userEvent.click(screen.getByRole('button', { name: /save revision/i }))
    expect(put.mock.calls[0][1].body.skills).toEqual([
      { name: 'Python', kind: 'technology', level: 'expert', years: 10 },
      { name: 'Rust', kind: 'technology', level: 'advanced', years: 3 },
    ])
  })

  it('adds a role and removes another', async () => {
    put.mockResolvedValue(saved())
    renderPanel()
    await userEvent.click(screen.getByRole('button', { name: /add role/i }))
    const titles = screen.getAllByLabelText('Role title')
    await userEvent.type(titles[1], 'Engineer')
    await userEvent.type(screen.getAllByLabelText('Role organisation')[1], 'Sample Systems')
    await userEvent.type(screen.getAllByLabelText('Role start')[1], '2014-02')
    await userEvent.click(screen.getByRole('button', { name: 'Remove role Solutions Architect' }))
    await userEvent.click(screen.getByRole('button', { name: /save revision/i }))
    expect(put.mock.calls[0][1].body.experience).toEqual([
      {
        title: 'Engineer',
        organisation: 'Sample Systems',
        start: '2014-02',
        end: null,
        summary: '',
        sectors: [],
      },
    ])
  })

  it('picking a base place fills the place, country, time zone and coordinates', async () => {
    put.mockResolvedValue(saved())
    renderPanel()
    await userEvent.type(screen.getByRole('combobox', { name: 'Base place' }), 'por')
    await userEvent.click(await screen.findByRole('option', { name: /Porto, Portugal/ }))
    await userEvent.click(screen.getByRole('button', { name: /save revision/i }))
    expect(put.mock.calls[0][1].body.base_location).toEqual({
      place: 'Porto, Portugal',
      country: 'PT',
      timezone: 'Europe/Lisbon',
      latitude: 41.1485,
      longitude: -8.61097,
    })
  })

  it('keeps education and certifications that it does not edit', async () => {
    put.mockResolvedValue(saved())
    renderPanel()
    expect(screen.getByText(/Example Certification/)).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Headline'), '!')
    await userEvent.click(screen.getByRole('button', { name: /save revision/i }))
    expect(put.mock.calls[0][1].body.education).toEqual([
      { level: 'msc', field: 'Computer Science' },
    ])
    expect(put.mock.calls[0][1].body.certifications).toEqual([
      { name: 'Example Certification', year: 2022 },
    ])
  })

  it('blocks saving an incomplete profile and says why', async () => {
    renderPanel()
    await userEvent.clear(screen.getByLabelText('Headline'))
    expect(screen.getByRole('button', { name: /save revision/i })).toBeDisabled()
    expect(screen.getByText('Add a headline.')).toBeInTheDocument()
  })

  it('a blank profile starts empty and its first save sends no expected revision', async () => {
    put.mockResolvedValue(saved())
    renderPanel(makeProfile({}, 0))
    expect(screen.getByLabelText('Headline')).toHaveValue('')
    await userEvent.type(screen.getByLabelText('Headline'), 'Engineer')
    await userEvent.type(screen.getByRole('combobox', { name: 'Base place' }), 'por')
    await userEvent.click(await screen.findByRole('option', { name: /Porto/ }))
    await userEvent.click(screen.getByRole('button', { name: /save revision/i }))
    expect(put.mock.calls[0][1].body.expected_current_revision).toBeNull()
  })

  it('reports a conflict from another save', async () => {
    put.mockResolvedValue({
      error: {
        error: {
          code: 'conflict',
          message: 'The profile changed since it was loaded.',
          details: {},
        },
      },
      response: { status: 409 },
    })
    renderPanel()
    await userEvent.type(screen.getByLabelText('Headline'), '!')
    await userEvent.click(screen.getByRole('button', { name: /save revision/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/changed since it was loaded/i)
  })

  it('exports the profile as a JSON download', async () => {
    get.mockResolvedValue({
      data: { schema_version: 1, profile: { title: 'AI Solutions' }, intents: [] },
    })
    renderPanel()
    await userEvent.click(screen.getByRole('button', { name: /export profile/i }))
    expect(get).toHaveBeenCalledWith('/api/v1/profiles/{career_profile_id}/export', {
      params: { path: { career_profile_id: 1 } },
    })
    await vi.waitFor(() => expect(download).toHaveBeenCalled())
    expect(download.mock.calls[0][0]).toMatch(/\.json$/)
  })

  it('deletes the profile data only after the exact title is typed', async () => {
    const user = userEvent.setup()
    del.mockResolvedValue({ data: { deleted: { career_profile: 1 } }, response: { status: 200 } })
    renderPanel(makeProfile({ title: 'AI Solutions' }))
    await user.click(screen.getByRole('button', { name: 'Delete profile data…' }))
    const confirm = screen.getByRole('button', { name: 'Delete permanently' })
    expect(confirm).toBeDisabled()
    await user.type(screen.getByLabelText(/type the profile title/i), 'ai solutions')
    expect(confirm).toBeDisabled() // case matters
    await user.clear(screen.getByLabelText(/type the profile title/i))
    await user.type(screen.getByLabelText(/type the profile title/i), 'AI Solutions')
    await user.click(confirm)
    expect(del).toHaveBeenCalledWith('/api/v1/profiles/{career_profile_id}', {
      params: { path: { career_profile_id: 1 }, query: { confirm: 'AI Solutions' } },
    })
  })

  it('can cancel the deletion', async () => {
    const user = userEvent.setup()
    renderPanel()
    await user.click(screen.getByRole('button', { name: 'Delete profile data…' }))
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByRole('button', { name: 'Delete permanently' })).not.toBeInTheDocument()
    expect(del).not.toHaveBeenCalled()
  })
})
