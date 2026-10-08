import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { StanceGroup } from './StanceGroup'

const terms = [
  { term_key: 'remote', label: 'Remote' },
  { term_key: 'hybrid', label: 'Hybrid' },
]

describe('StanceGroup (closed group)', () => {
  const value = [
    { key: 'remote', stance: 'preferred' as const },
    { key: 'hybrid', stance: 'acceptable' as const },
  ]

  it('shows one labelled choice of Preferred, OK or Reject per option', () => {
    render(<StanceGroup label="Work arrangement" terms={terms} value={value} onChange={vi.fn()} />)
    const remote = screen.getByRole('radiogroup', { name: 'Remote' })
    expect(remote).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Preferred', checked: true })).toBeInTheDocument()
    expect(screen.getAllByRole('radio', { name: 'Reject' })).toHaveLength(2)
    expect(screen.queryByRole('radio', { name: 'No opinion' })).not.toBeInTheDocument()
  })

  it('reports the new list when one option changes', async () => {
    const onChange = vi.fn()
    render(<StanceGroup label="Work arrangement" terms={terms} value={value} onChange={onChange} />)
    const hybrid = screen.getByRole('radiogroup', { name: 'Hybrid' })
    await userEvent.click(hybrid.querySelector('input[value="rejected"]')!)
    expect(onChange).toHaveBeenCalledWith([
      { key: 'remote', stance: 'preferred' },
      { key: 'hybrid', stance: 'rejected' },
    ])
  })

  it('warns when everything is rejected, because such an intent can never match', () => {
    const all = value.map((entry) => ({ ...entry, stance: 'rejected' as const }))
    render(<StanceGroup label="Work arrangement" terms={terms} value={all} onChange={vi.fn()} />)
    expect(screen.getByRole('alert')).toHaveTextContent(/at least one option/i)
  })

  it('does not warn while at least one option is not rejected', () => {
    render(<StanceGroup label="Work arrangement" terms={terms} value={value} onChange={vi.fn()} />)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})

describe('StanceGroup (open group)', () => {
  it('lets an option have no opinion, which removes it from the list', async () => {
    const onChange = vi.fn()
    render(
      <StanceGroup
        label="Sectors"
        terms={terms}
        value={[{ key: 'remote', stance: 'preferred' }]}
        onChange={onChange}
        allowNoOpinion
      />,
    )
    const hybrid = screen.getByRole('radiogroup', { name: 'Hybrid' })
    expect(hybrid.querySelector('input[value="none"]')).toBeChecked() // not listed = no opinion
    await userEvent.click(
      screen.getByRole('radiogroup', { name: 'Remote' }).querySelector('input[value="none"]')!,
    )
    expect(onChange).toHaveBeenCalledWith([])
  })

  it('adds an option when it gets an opinion', async () => {
    const onChange = vi.fn()
    render(
      <StanceGroup label="Sectors" terms={terms} value={[]} onChange={onChange} allowNoOpinion />,
    )
    await userEvent.click(
      screen.getByRole('radiogroup', { name: 'Hybrid' }).querySelector('input[value="rejected"]')!,
    )
    expect(onChange).toHaveBeenCalledWith([{ key: 'hybrid', stance: 'rejected' }])
  })

  it('an empty open group is fine and shows no warning', () => {
    render(
      <StanceGroup label="Sectors" terms={terms} value={[]} onChange={vi.fn()} allowNoOpinion />,
    )
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
