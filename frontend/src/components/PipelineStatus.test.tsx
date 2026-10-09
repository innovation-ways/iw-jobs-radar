import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { PipelineStatus as Status } from '@/features/pipeline/summary'
import { PipelineStatus } from './PipelineStatus'

const get = vi.fn()
vi.mock('@/api/client', () => ({ api: { GET: (...args: unknown[]) => get(...args) } }))

const base: Status = {
  state: 'working',
  ai_model: 'qwen3:8b',
  worker: { status: 'up', last_beat_at: '2026-10-09T12:00:00Z' },
  analysis: {
    total: 653,
    done: 211,
    failed: 2,
    waiting: 440,
    search_intent_id: null,
    minutes_left: 147,
  },
  scoring: { total: 211, done: 40, failed: 0, waiting: 171, search_intent_id: 4, minutes_left: 30 },
  recent: {
    window_minutes: 15,
    analysed: 45,
    scored: 12,
    analysed_per_minute: 3,
    scored_per_minute: 0.8,
  },
  failures: {
    count: 2,
    last_error_class: 'schema_invalid',
    last_failed_at: '2026-10-09T11:50:00Z',
  },
  generated_at: '2026-10-09T12:00:10Z',
}

function renderStatus() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <PipelineStatus />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('PipelineStatus', () => {
  beforeEach(() => {
    get.mockReset()
    get.mockResolvedValue({ data: base })
  })

  it('summarises the work in one line with its pace', async () => {
    renderStatus()
    expect(await screen.findByText('Analysing 211 of 653')).toBeInTheDocument()
    expect(screen.getByText('3/min · ~2 h 27 min left')).toBeInTheDocument()
  })

  it('opens the details with both stages, the worker and the last failure', async () => {
    renderStatus()
    await userEvent.click(await screen.findByRole('button', { name: /analysing 211 of 653/i }))
    const details = screen.getByRole('region', { name: /pipeline details/i })
    expect(within(details).getByText('211 of 653 analysed')).toBeInTheDocument()
    expect(within(details).getByText(/440 waiting/)).toBeInTheDocument()
    expect(within(details).getByText('40 of 211 scored')).toBeInTheDocument()
    expect(within(details).getByText(/2 failed/)).toBeInTheDocument()
    expect(within(details).getByText(/schema_invalid/)).toBeInTheDocument()
    expect(within(details).getByText(/qwen3:8b/)).toBeInTheDocument()
    expect(within(details).getByText(/worker up/i)).toBeInTheDocument()
    expect(within(details).getByRole('link', { name: /jobs not evaluated/i })).toHaveAttribute(
      'href',
      '/inbox?fit=unscored',
    )
  })

  it('says in words when the worker does not respond', async () => {
    get.mockResolvedValue({
      data: { ...base, state: 'worker_stopped', worker: { status: 'stale', last_beat_at: null } },
    })
    renderStatus()
    expect(await screen.findByText('Worker not responding')).toBeInTheDocument()
  })

  it('shows nothing alarming while the first answer is pending or when it fails', async () => {
    get.mockRejectedValue(new Error('down'))
    renderStatus()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})
