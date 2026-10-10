import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { AnalysisCard, WebsiteForm, type AnalysisValue } from './CompanyAnalysis'

const value: AnalysisValue = {
  statements: [
    {
      topic: 'remote_policy',
      text: 'Remote-first.',
      quote: 'We are remote-first',
      page_url: 'https://northwind.example/about',
    },
    {
      topic: 'portugal_presence',
      text: 'Has a Lisbon hub.',
      quote: 'a hub in Lisbon',
      page_url: 'https://northwind.example/about',
    },
  ],
  open_questions: ['Salary bands are not published.'],
  pages: ['https://northwind.example/', 'https://northwind.example/about'],
  dropped: 2,
}

describe('AnalysisCard', () => {
  it('groups statements by topic and shows each quote with its page', () => {
    render(
      <AnalysisCard value={value} model="ollama:qwen3:8b" retrievedAt="2026-10-10T08:00:00Z" />,
    )
    expect(screen.getByText('AI inference')).toBeInTheDocument()
    expect(screen.getByText('Remote or hybrid policy')).toBeInTheDocument()
    expect(screen.getByText('Presence in Portugal')).toBeInTheDocument()
    expect(screen.getByText('Remote-first.')).toBeInTheDocument()
    expect(screen.getByText(/“We are remote-first”/)).toBeInTheDocument()
    const link = screen.getAllByRole('link', { name: /northwind.example\/about/ })[0]
    expect(link).toHaveAttribute('href', 'https://northwind.example/about')
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'))
  })

  it('lists open questions and says how many statements were dropped', () => {
    render(
      <AnalysisCard value={value} model="ollama:qwen3:8b" retrievedAt="2026-10-10T08:00:00Z" />,
    )
    expect(screen.getByText('Salary bands are not published.')).toBeInTheDocument()
    expect(
      screen.getByText(/2 statements without a matching quote were dropped/),
    ).toBeInTheDocument()
    expect(screen.getByText(/2 pages read/)).toBeInTheDocument()
  })

  it('does not break on a stored value of an unexpected shape', () => {
    render(<AnalysisCard value={'oops'} model="m" retrievedAt="2026-10-10T08:00:00Z" />)
    expect(screen.getByText(/could not be shown/)).toBeInTheDocument()
  })
})

describe('WebsiteForm', () => {
  it('submits the typed address and clears nothing it was not asked to', async () => {
    const onSubmit = vi.fn()
    render(<WebsiteForm pending={false} onSubmit={onSubmit} />)
    await userEvent.type(screen.getByLabelText('Company website'), 'northwind.example')
    await userEvent.click(screen.getByRole('button', { name: 'Save website' }))
    expect(onSubmit).toHaveBeenCalledWith('northwind.example')
  })

  it('does not submit an empty address', async () => {
    const onSubmit = vi.fn()
    render(<WebsiteForm pending={false} onSubmit={onSubmit} />)
    expect(screen.getByRole('button', { name: 'Save website' })).toBeDisabled()
  })
})
