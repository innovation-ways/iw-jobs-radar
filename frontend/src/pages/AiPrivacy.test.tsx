import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AiPrivacy } from './AiPrivacy'

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

function connection(overrides: Record<string, unknown> = {}) {
  return {
    provider_connection_id: 1,
    provider_type: 'openai',
    display_name: 'OpenAI',
    endpoint_url: 'https://api.openai.com/v1',
    model_id: 'gpt-test',
    credential_status: 'none',
    credential_updated_at: null,
    processing_location: 'remote',
    is_active: false,
    use_for_jobs: false,
    version: 1,
    ...overrides,
  }
}

const local = connection({
  provider_connection_id: 2,
  provider_type: 'ollama',
  display_name: 'Local Ollama',
  endpoint_url: 'http://host.docker.internal:11434',
  model_id: 'qwen3:8b',
  processing_location: 'local',
})

let settings: Record<string, unknown>

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <AiPrivacy />
    </QueryClientProvider>,
  )
}

describe('AI & privacy screen', () => {
  beforeEach(() => {
    for (const m of [get, post, put, del]) m.mockReset()
    settings = {
      mode: 'no_ai',
      import_connection_id: null,
      jobs_connection_id: null,
      key_configured: true,
      connections: [],
      privacy: { redact_contact_details: true, version: 1 },
      integrations: { github: 'none' },
    }
    get.mockImplementation(() => Promise.resolve({ data: settings }))
  })

  it('starts as No AI and explains what that means', async () => {
    renderPage()
    expect(await screen.findByText(/jobs are still collected/i)).toBeInTheDocument()
    expect(screen.getByText(/uploaded cvs are never stored/i)).toBeInTheDocument()
  })

  it('warns when the credential key is missing', async () => {
    settings = { ...settings, key_configured: false }
    renderPage()
    expect(await screen.findByRole('alert')).toHaveTextContent(/JOBS_RADAR_CREDENTIAL_KEY/)
  })

  it('adds a connection with the typed fields', async () => {
    const user = userEvent.setup()
    post.mockResolvedValue({ data: connection() })
    renderPage()
    await screen.findByText(/jobs are still collected/i)
    await user.selectOptions(screen.getByLabelText('Provider'), 'openai')
    await user.type(screen.getByLabelText('Name'), 'Work OpenAI')
    await user.type(screen.getByLabelText('Model'), 'gpt-test')
    await user.click(screen.getByRole('button', { name: 'Add connection' }))
    expect(post).toHaveBeenCalledWith('/api/v1/settings/ai/connections', {
      body: {
        provider_type: 'openai',
        display_name: 'Work OpenAI',
        endpoint_url: null,
        model_id: 'gpt-test',
      },
    })
  })

  it('stores a credential write-only and shows only its status', async () => {
    const user = userEvent.setup()
    settings = { ...settings, connections: [connection()] }
    put.mockResolvedValue({ data: connection({ credential_status: 'saved' }) })
    renderPage()
    const card = (await screen.findByRole('heading', { name: 'OpenAI' })).closest('section')!
    expect(within(card).getByText('Credential: not set')).toBeInTheDocument()
    const input = within(card).getByLabelText('API key')
    expect(input).toHaveAttribute('type', 'password')
    await user.type(input, 'sk-secret-value')
    await user.click(within(card).getByRole('button', { name: 'Save key' }))
    expect(put).toHaveBeenCalledWith(
      '/api/v1/settings/ai/connections/{provider_connection_id}/credential',
      { params: { path: { provider_connection_id: 1 } }, body: { secret: 'sk-secret-value' } },
    )
    expect(input).toHaveValue('') // never kept on screen after saving
    expect(document.body).not.toHaveTextContent('sk-secret-value')
  })

  it('shows a saved credential as saved and can remove it', async () => {
    const user = userEvent.setup()
    settings = { ...settings, connections: [connection({ credential_status: 'saved' })] }
    del.mockResolvedValue({ data: connection() })
    renderPage()
    const card = (await screen.findByRole('heading', { name: 'OpenAI' })).closest('section')!
    expect(within(card).getByText('Credential: saved')).toBeInTheDocument()
    await user.click(within(card).getByRole('button', { name: 'Remove key' }))
    expect(del).toHaveBeenCalledWith(
      '/api/v1/settings/ai/connections/{provider_connection_id}/credential',
      { params: { path: { provider_connection_id: 1 } } },
    )
  })

  it('tests a connection, lists the models and lets the owner type one if none are listed', async () => {
    const user = userEvent.setup()
    settings = { ...settings, connections: [connection({ credential_status: 'saved' })] }
    post.mockResolvedValue({
      data: {
        ok: true,
        error_class: null,
        message: 'Connected; 2 models available.',
        models: ['m-1', 'm-2'],
      },
    })
    renderPage()
    const card = (await screen.findByRole('heading', { name: 'OpenAI' })).closest('section')!
    await user.click(within(card).getByRole('button', { name: 'Test connection' }))
    expect(await within(card).findByText(/connected; 2 models/i)).toBeInTheDocument()
    expect(within(card).getByRole('option', { name: 'm-2' })).toBeInTheDocument()
  })

  it('reports a failed test with its reason', async () => {
    const user = userEvent.setup()
    settings = { ...settings, connections: [connection({ credential_status: 'saved' })] }
    post.mockResolvedValue({
      data: {
        ok: false,
        error_class: 'unauthorized',
        message: 'The AI provider refused the credential.',
        models: [],
      },
    })
    renderPage()
    const card = (await screen.findByRole('heading', { name: 'OpenAI' })).closest('section')!
    await user.click(within(card).getByRole('button', { name: 'Test connection' }))
    expect(await within(card).findByRole('alert')).toHaveTextContent(/refused the credential/i)
  })

  it('chooses the CV import connection, labelling remote ones as leaving the machine', async () => {
    const user = userEvent.setup()
    settings = {
      ...settings,
      connections: [connection({ credential_status: 'saved' }), local],
    }
    put.mockResolvedValue({ data: settings })
    renderPage()
    const select = await screen.findByLabelText('CV import')
    expect(within(select).getByRole('option', { name: /OpenAI · remote/ })).toBeInTheDocument()
    expect(
      within(select).getByRole('option', { name: /Local Ollama · this machine/ }),
    ).toBeInTheDocument()
    await user.selectOptions(select, '1')
    expect(put).toHaveBeenCalledWith('/api/v1/settings/ai/import-connection', {
      body: { provider_connection_id: 1 },
    })
  })

  it('offers only local connections for job analysis', async () => {
    const user = userEvent.setup()
    settings = { ...settings, connections: [connection({ credential_status: 'saved' }), local] }
    put.mockResolvedValue({ data: settings })
    renderPage()
    const select = await screen.findByLabelText('Job analysis')
    expect(within(select).queryByRole('option', { name: /OpenAI/ })).not.toBeInTheDocument()
    await user.selectOptions(select, '2')
    expect(put).toHaveBeenCalledWith('/api/v1/settings/ai/jobs-connection', {
      body: { provider_connection_id: 2 },
    })
  })

  it('changes the redaction policy with the version it saw', async () => {
    const user = userEvent.setup()
    put.mockResolvedValue({ data: { redact_contact_details: false, version: 2 } })
    renderPage()
    const toggle = await screen.findByRole('checkbox', { name: /remove contact details/i })
    expect(toggle).toBeChecked()
    await user.click(toggle)
    expect(put).toHaveBeenCalledWith('/api/v1/settings/privacy', {
      body: { redact_contact_details: false, expected_version: 1 },
    })
  })

  it('stores the optional GitHub token write-only', async () => {
    const user = userEvent.setup()
    put.mockResolvedValue({ data: { github: 'saved' } })
    renderPage()
    const input = await screen.findByLabelText('GitHub token')
    expect(input).toHaveAttribute('type', 'password')
    expect(screen.getByText('GitHub token: not set')).toBeInTheDocument()
    await user.type(input, 'ghp_secret_value')
    await user.click(screen.getByRole('button', { name: 'Save token' }))
    expect(put).toHaveBeenCalledWith('/api/v1/settings/integrations/{name}/credential', {
      params: { path: { name: 'github' } },
      body: { secret: 'ghp_secret_value' },
    })
    expect(input).toHaveValue('')
    expect(document.body).not.toHaveTextContent('ghp_secret_value')
  })
})
