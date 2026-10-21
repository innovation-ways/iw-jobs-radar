import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ImportCvPanel } from './ImportCvPanel'

const get = vi.fn()
const post = vi.fn()
vi.mock('@/api/client', () => ({
  api: { GET: (...a: unknown[]) => get(...a), POST: (...a: unknown[]) => post(...a) },
}))
const fetchMock = vi.fn()

const profile = {
  career_profile_id: 7,
  title: 'Main',
  visibility: 'private',
  version: 1,
  current_revision: { revision_number: 3 },
} as never

function connection(kind: 'local' | 'remote') {
  return {
    provider_connection_id: kind === 'local' ? 2 : 1,
    provider_type: kind === 'local' ? 'ollama' : 'openai',
    display_name: kind === 'local' ? 'Local Ollama' : 'OpenAI',
    endpoint_url: 'x',
    model_id: kind === 'local' ? 'qwen3:8b' : 'gpt-test',
    credential_status: kind === 'local' ? 'none' : 'saved',
    credential_updated_at: null,
    processing_location: kind,
    is_active: true,
    use_for_jobs: false,
    version: 1,
  }
}

function settings(active: 'none' | 'local' | 'remote', redact = true) {
  const connections = active === 'none' ? [] : [connection(active)]
  return {
    mode: active === 'none' ? 'no_ai' : active,
    import_connection_id: connections[0]?.provider_connection_id ?? null,
    jobs_connection_id: null,
    key_configured: true,
    connections,
    privacy: { redact_contact_details: redact, version: 1 },
  }
}

const documentInfo = {
  document_id: 40,
  sha256: 'a'.repeat(64),
  mime_type: 'application/pdf',
  byte_size: 20480,
  extraction_status: 'extracted',
  extraction_version: 'extract-v1',
  pages: 2,
  characters: 1800,
  text_available: true,
  created_at: '2026-10-08T10:00:00Z',
}

function item(id: number, path: string, value: unknown, excerpt: string | null = 'a quote') {
  return {
    proposal_item_id: id,
    path,
    value,
    source_excerpt: excerpt,
    confidence: 0.9,
    review_status: 'pending',
    edited_value: null,
    reviewed_at: null,
  }
}

const proposal = {
  profile_proposal_id: 5,
  career_profile_id: 7,
  document_id: 40,
  provider_type: 'ollama',
  provider_model: 'qwen3:8b',
  prompt_version: 'profile-import-v1',
  redaction_policy: null,
  consent: null,
  status: 'pending',
  completed_at: null,
  created_at: '2026-10-08T10:01:00Z',
  items: [
    item(11, 'headline', 'Senior Software Engineer', 'Senior Software Engineer'),
    item(12, 'skills', { name: 'Python', kind: 'technology', level: 'expert', years: 8 }),
  ],
}

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ImportCvPanel profile={profile} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

async function chooseFile(user: ReturnType<typeof userEvent.setup>) {
  const file = new File(['pdf'], 'my-cv.pdf', { type: 'application/pdf' })
  await user.upload(screen.getByLabelText('Choose a CV file'), file)
}

describe('Import CV', () => {
  beforeEach(() => {
    for (const m of [get, post, fetchMock]) m.mockReset()
    vi.stubGlobal('fetch', fetchMock)
    get.mockResolvedValue({ data: settings('local') })
    fetchMock.mockResolvedValue({
      ok: true,
      status: 201,
      json: () => Promise.resolve(documentInfo),
    })
  })
  afterEach(() => vi.unstubAllGlobals())

  it('says what is needed when no AI connection is chosen', async () => {
    get.mockResolvedValue({ data: settings('none') })
    renderPanel()
    expect(await screen.findByText(/choose an ai connection/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /ai & privacy/i })).toHaveAttribute('href', '/settings')
    expect(screen.getByLabelText('Choose a CV file')).toBeDisabled()
  })

  it('explains next to the drop area why it is off, and the browse button is off too', async () => {
    get.mockResolvedValue({ data: settings('none') })
    renderPanel()
    expect(await screen.findByRole('button', { name: /browse/i })).toBeDisabled()
    expect(screen.getByText(/importing a cv is off until/i)).toBeInTheDocument()
  })

  it('has a browse button that opens the file chooser', async () => {
    const user = userEvent.setup()
    renderPanel()
    const input = (await screen.findByLabelText('Choose a CV file')) as HTMLInputElement
    const click = vi.spyOn(input, 'click')
    await user.click(screen.getByRole('button', { name: /browse/i }))
    expect(click).toHaveBeenCalled()
  })

  it('uploads a CV dropped on the drop area', async () => {
    renderPanel()
    const zone = await screen.findByTestId('cv-drop-area')
    const file = new File(['pdf'], 'dropped.pdf', { type: 'application/pdf' })
    fireEvent.drop(zone, { dataTransfer: { files: [file] } })
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    expect(await screen.findByText(/dropped\.pdf/)).toBeInTheDocument()
  })

  it('does not upload a drop while no AI connection is chosen', async () => {
    get.mockResolvedValue({ data: settings('none') })
    renderPanel()
    const zone = await screen.findByTestId('cv-drop-area')
    const file = new File(['pdf'], 'dropped.pdf', { type: 'application/pdf' })
    fireEvent.drop(zone, { dataTransfer: { files: [file] } })
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('keeps the browser from opening a file that is dropped outside the drop area', async () => {
    renderPanel()
    await screen.findByTestId('cv-drop-area')
    const event = new Event('drop', { cancelable: true })
    window.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(true)
  })

  it('shows where processing happens and that the original is not stored', async () => {
    renderPanel()
    expect(await screen.findByText(/original file is not stored/i)).toBeInTheDocument()
    expect(screen.getByText(/this machine · qwen3:8b/)).toBeInTheDocument()
  })

  it('uploads a file, shows safe metadata and generates proposals locally without consent', async () => {
    const user = userEvent.setup()
    post.mockResolvedValue({ data: proposal })
    renderPanel()
    await screen.findByText(/original file is not stored/i)
    await chooseFile(user)
    expect(await screen.findByText(/my-cv\.pdf/)).toBeInTheDocument()
    expect(screen.getByText(/2 pages/)).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/documents',
      expect.objectContaining({ method: 'POST' }),
    )
    await user.click(screen.getByRole('button', { name: 'Generate proposals' }))
    expect(post).toHaveBeenCalledWith('/api/v1/documents/{document_id}/proposals', {
      params: { path: { document_id: 40 } },
      body: { career_profile_id: 7, consent: null },
    })
    expect(await screen.findByText('Senior Software Engineer')).toBeInTheDocument()
    expect(screen.getByText(/Python · expert · 8 years/)).toBeInTheDocument()
  })

  it('requires explicit consent before a remote provider gets the CV', async () => {
    const user = userEvent.setup()
    get.mockResolvedValue({ data: settings('remote') })
    post.mockResolvedValue({ data: { ...proposal, redaction_policy: 'contact-v1' } })
    renderPanel()
    await screen.findByLabelText('Choose a CV file')
    await chooseFile(user)
    const box = await screen.findByRole('group', { name: /before this cv leaves your machine/i })
    expect(within(box).getByText(/Sent to: OpenAI/)).toBeInTheDocument()
    expect(within(box).getByText(/model gpt-test/)).toBeInTheDocument()
    expect(within(box).getByText(/contact details are removed/i)).toBeInTheDocument()
    const generate = screen.getByRole('button', { name: 'Generate proposals' })
    expect(generate).toBeDisabled()
    await user.click(within(box).getByRole('checkbox'))
    await user.click(generate)
    expect(post).toHaveBeenCalledWith('/api/v1/documents/{document_id}/proposals', {
      params: { path: { document_id: 40 } },
      body: { career_profile_id: 7, consent: { provider_connection_id: 1, model_id: 'gpt-test' } },
    })
  })

  it('warns that contact details are sent when redaction is off', async () => {
    get.mockResolvedValue({ data: settings('remote', false) })
    const user = userEvent.setup()
    renderPanel()
    await screen.findByLabelText('Choose a CV file')
    await chooseFile(user)
    expect(await screen.findByText(/contact details are not removed/i)).toBeInTheDocument()
  })

  it('explains a scanned PDF', async () => {
    const user = userEvent.setup()
    fetchMock.mockResolvedValue({
      ok: true,
      status: 201,
      json: () =>
        Promise.resolve({ ...documentInfo, extraction_status: 'needs_ocr', text_available: false }),
    })
    renderPanel()
    await screen.findByLabelText('Choose a CV file')
    await chooseFile(user)
    expect(await screen.findByText(/scan.*no text|no text/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Generate proposals' })).not.toBeInTheDocument()
  })

  it('reports an upload the server refused', async () => {
    const user = userEvent.setup()
    fetchMock.mockResolvedValue({
      ok: false,
      status: 422,
      json: () =>
        Promise.resolve({
          error: {
            code: 'validation_error',
            message: 'Only PDF, Word (.docx), .txt and .md files are accepted.',
            details: {},
          },
        }),
    })
    renderPanel()
    await screen.findByLabelText('Choose a CV file')
    await chooseFile(user)
    expect(await screen.findByRole('alert')).toHaveTextContent(/only pdf, word/i)
  })

  it('reviews items and applies the decisions against the revision it saw', async () => {
    const user = userEvent.setup()
    post.mockImplementation((path: string) =>
      Promise.resolve({
        data: path.includes('proposals')
          ? proposal
          : {
              created: true,
              profile: { career_profile_id: 7, current_revision: { revision_number: 4 } },
              proposal: { ...proposal, status: 'completed' },
            },
      }),
    )
    renderPanel()
    await screen.findByLabelText('Choose a CV file')
    await chooseFile(user)
    await user.click(await screen.findByRole('button', { name: 'Generate proposals' }))
    const headline = await screen.findByRole('radiogroup', { name: /Headline/ })
    const skill = screen.getByRole('radiogroup', { name: /Skill/ })
    await user.click(within(headline).getByLabelText('Accept'))
    await user.click(within(skill).getByLabelText('Edit'))
    const years = screen.getByLabelText(/Skill: Python.*: years/)
    await user.clear(years)
    await user.type(years, '10')
    expect(screen.getByText('2 of 2 decided')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /apply review/i }))
    expect(post).toHaveBeenLastCalledWith('/api/v1/profiles/{career_profile_id}/reviews', {
      params: { path: { career_profile_id: 7 } },
      body: {
        profile_proposal_id: 5,
        expected_current_revision: 3,
        decisions: [
          { proposal_item_id: 11, decision: 'accept' },
          {
            proposal_item_id: 12,
            decision: 'edit',
            value: { name: 'Python', kind: 'technology', level: 'expert', years: 10 },
          },
        ],
      },
    })
    expect(await screen.findByText(/revision 4 was created/i)).toBeInTheDocument()
  })

  it('edits a skill level with a dropdown of the allowed values', async () => {
    const user = userEvent.setup()
    post.mockResolvedValue({ data: proposal })
    renderPanel()
    await screen.findByLabelText('Choose a CV file')
    await chooseFile(user)
    await user.click(await screen.findByRole('button', { name: 'Generate proposals' }))
    await user.click(
      within(await screen.findByRole('radiogroup', { name: /Skill/ })).getByLabelText('Edit'),
    )
    const level = screen.getByLabelText(/Skill: Python.*: level/)
    expect(level.tagName).toBe('SELECT')
    expect(
      within(level)
        .getAllByRole('option')
        .map((o) => o.textContent),
    ).toEqual(['beginner', 'intermediate', 'advanced', 'expert'])
    await user.selectOptions(level, 'advanced')
    expect(level).toHaveValue('advanced')
  })

  it('does not allow applying before something is decided', async () => {
    const user = userEvent.setup()
    post.mockResolvedValue({ data: proposal })
    renderPanel()
    await screen.findByLabelText('Choose a CV file')
    await chooseFile(user)
    await user.click(await screen.findByRole('button', { name: 'Generate proposals' }))
    expect(await screen.findByRole('button', { name: /apply review/i })).toBeDisabled()
  })

  it('keeps the hidden decision radios inside their label so focusing one never scrolls the page', async () => {
    const user = userEvent.setup()
    post.mockResolvedValue({ data: proposal })
    renderPanel()
    await screen.findByLabelText('Choose a CV file')
    await chooseFile(user)
    await user.click(await screen.findByRole('button', { name: 'Generate proposals' }))
    const headline = await screen.findByRole('radiogroup', { name: /Headline/ })
    // An absolutely positioned radio without a positioned ancestor lands outside the scrolling
    // <main>, so focusing it scrolls the whole document and cuts the page in half.
    expect(within(headline).getByLabelText('Accept').closest('label')).toHaveClass('relative')
  })

  it('accepts every undecided item at once and keeps explicit choices', async () => {
    const user = userEvent.setup()
    post.mockImplementation((path: string) =>
      Promise.resolve({
        data: path.includes('proposals')
          ? proposal
          : {
              created: true,
              profile: { career_profile_id: 7, current_revision: { revision_number: 4 } },
              proposal: { ...proposal, status: 'completed' },
            },
      }),
    )
    renderPanel()
    await screen.findByLabelText('Choose a CV file')
    await chooseFile(user)
    await user.click(await screen.findByRole('button', { name: 'Generate proposals' }))
    const skill = await screen.findByRole('radiogroup', { name: /Skill/ })
    await user.click(within(skill).getByLabelText('Reject'))
    await user.click(screen.getByRole('button', { name: 'Accept all undecided' }))
    expect(screen.getByText('2 of 2 decided')).toBeInTheDocument()
    expect(
      within(screen.getByRole('radiogroup', { name: /Headline/ })).getByLabelText('Accept'),
    ).toBeChecked()
    expect(within(skill).getByLabelText('Reject')).toBeChecked()
    await user.click(screen.getByRole('button', { name: /apply review/i }))
    expect(post).toHaveBeenLastCalledWith(
      '/api/v1/profiles/{career_profile_id}/reviews',
      expect.objectContaining({
        body: expect.objectContaining({
          decisions: [
            { proposal_item_id: 11, decision: 'accept' },
            { proposal_item_id: 12, decision: 'reject' },
          ],
        }),
      }),
    )
  })
})
