import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { TAXONOMY, makeIntent } from '@/test/builders'
import { IntentPanel } from './IntentPanel'

const put = vi.fn()
const post = vi.fn()
vi.mock('@/api/client', () => ({
  api: {
    PUT: (...args: unknown[]) => put(...args),
    POST: (...args: unknown[]) => post(...args),
    GET: vi.fn().mockResolvedValue({ data: { items: [] } }),
  },
}))

function renderPanel(section: 'intent' | 'weights' = 'intent', intent = makeIntent()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <IntentPanel intent={intent} taxonomy={TAXONOMY} section={section} />
    </QueryClientProvider>,
  )
}

const envelope = (message: string) => ({
  error: { error: { code: 'x', message, details: {} } },
  response: { status: 409 },
})

describe('IntentPanel', () => {
  beforeEach(() => {
    put.mockReset()
    post.mockReset()
  })

  it('shows every section of the intent and no save bar until something changes', () => {
    renderPanel()
    for (const title of [
      'Roles',
      'Work arrangement & location',
      'Engagement',
      'Compensation',
      'Seniority',
      'Schedule & travel',
      'Domain & sector',
      'Employer',
      'Languages',
      'Other',
    ]) {
      expect(screen.getByRole('heading', { name: title })).toBeInTheDocument()
    }
    expect(screen.queryByRole('region', { name: /unsaved/i })).not.toBeInTheDocument()
    expect(screen.getByText(/revision 1/i)).toBeInTheDocument()
  })

  it('saves the draft as the next revision with the revision the owner saw', async () => {
    put.mockResolvedValue({
      data: { created: true, intent: makeIntent() },
      response: { status: 200 },
    })
    renderPanel()
    const name = screen.getByLabelText('Intent name')
    await userEvent.clear(name)
    await userEvent.type(name, 'Remote first')
    await userEvent.type(screen.getByLabelText(/change note/i), 'Renamed')
    await userEvent.click(screen.getByRole('button', { name: /save revision/i }))

    expect(put).toHaveBeenCalledTimes(1)
    const [path, options] = put.mock.calls[0]
    expect(path).toBe('/api/v1/intents/{search_intent_id}')
    expect(options.params).toEqual({ path: { search_intent_id: 5 } })
    expect(options.body).toMatchObject({
      title: 'Remote first',
      expected_current_revision: 1,
      change_summary: 'Renamed',
    })
    expect(options.body.stances.work_arrangements).toHaveLength(3)
  })

  it('lets the owner rule out jobs that need a licence they do not hold (off by default)', async () => {
    put.mockResolvedValue({
      data: { created: true, intent: makeIntent() },
      response: { status: 200 },
    })
    renderPanel()
    const toggle = screen.getByRole('checkbox', {
      name: /rule out jobs that require a licence or certification i do not hold/i,
    })
    expect(toggle).not.toBeChecked()
    await userEvent.click(toggle)
    await userEvent.click(screen.getByRole('button', { name: /save revision/i }))
    expect(put.mock.calls[0][1].body.filters.reject_missing_credentials).toBe(true)
  })

  it('discarding restores the saved values', async () => {
    renderPanel()
    const name = screen.getByLabelText('Intent name')
    await userEvent.type(name, ' edited')
    await userEvent.click(screen.getByRole('button', { name: /discard/i }))
    expect(name).toHaveValue('My search')
    expect(screen.queryByRole('region', { name: /unsaved/i })).not.toBeInTheDocument()
  })

  it('changing a stance marks the draft as changed', async () => {
    renderPanel()
    const remote = screen.getAllByRole('radiogroup', { name: 'Remote' })[0]
    await userEvent.click(within(remote).getByRole('radio', { name: 'Preferred' }))
    expect(screen.getByRole('region', { name: /unsaved/i })).toBeInTheDocument()
  })

  it('does not allow saving an intent that could never match and explains why', async () => {
    renderPanel()
    for (const group of ['Remote', 'Hybrid', 'On-site']) {
      const radios = screen.getAllByRole('radiogroup', { name: group })
      await userEvent.click(within(radios[0]).getByRole('radio', { name: 'Reject' }))
    }
    expect(screen.getByRole('button', { name: /save revision/i })).toBeDisabled()
    expect(screen.getAllByText(/at least one option must not be rejected/i).length).toBeGreaterThan(
      0,
    )
  })

  it('shows a version conflict and keeps the draft', async () => {
    put.mockResolvedValue(envelope('The intent changed since it was loaded.'))
    renderPanel()
    await userEvent.type(screen.getByLabelText('Intent name'), ' x')
    await userEvent.click(screen.getByRole('button', { name: /save revision/i }))
    const bar = await screen.findByRole('region', { name: /unsaved/i })
    expect(await within(bar).findByRole('alert')).toHaveTextContent(/changed since it was loaded/i)
    expect(screen.getByLabelText('Intent name')).toHaveValue('My search x')
  })

  it('adds a region and a keyword to the draft', async () => {
    renderPanel()
    await userEvent.type(screen.getByLabelText('Remote regions'), 'uk{Enter}')
    await userEvent.type(screen.getByLabelText('Helpful keywords'), 'billing{Enter}')
    expect(screen.getByText('UK')).toBeInTheDocument()
    expect(screen.getByText('billing')).toBeInTheDocument()
    expect(screen.getByRole('region', { name: /unsaved/i })).toBeInTheDocument()
  })

  it('disables and enables the intent with its version', async () => {
    post.mockResolvedValue({ data: makeIntent({ enabled: false }), response: { status: 200 } })
    renderPanel()
    await userEvent.click(screen.getByRole('button', { name: 'Disable' }))
    expect(post).toHaveBeenCalledWith('/api/v1/intents/{search_intent_id}/disable', {
      params: { path: { search_intent_id: 5 } },
      body: { expected_version: 1 },
    })
  })

  it('edits weights in the weights section and saves them with the intent', async () => {
    put.mockResolvedValue({
      data: { created: true, intent: makeIntent() },
      response: { status: 200 },
    })
    renderPanel('weights')
    fireEvent.change(screen.getByRole('slider', { name: 'Compensation weight' }), {
      target: { value: '30' },
    })
    await userEvent.click(screen.getByRole('button', { name: /save revision/i }))
    expect(put.mock.calls[0][1].body.weights.compensation).toBe(30)
  })

  it('blocks saving when every weight is zero', () => {
    renderPanel('weights')
    for (const slider of screen.getAllByRole('slider'))
      fireEvent.change(slider, { target: { value: '0' } })
    expect(screen.getByRole('button', { name: /save revision/i })).toBeDisabled()
    expect(screen.getAllByText(/at least one weight must be above 0/i).length).toBeGreaterThan(0)
  })
})
