import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { StanceGroup } from './StanceGroup'

const terms = [
  { term_key: 'new', label: 'New family' },
  { term_key: 'other', label: 'Other family' },
]

describe('StanceGroup after a merge', () => {
  it('shows the stance chosen for the merged term on the term that replaced it', () => {
    render(
      <StanceGroup
        label="Roles"
        terms={terms}
        value={[{ key: 'old', stance: 'preferred' }]}
        replacements={{ old: 'new' }}
        onChange={vi.fn()}
        allowNoOpinion
      />,
    )
    const group = screen.getByRole('radiogroup', { name: 'New family' })
    expect(group.querySelector('input[value="preferred"]')).toBeChecked()
  })

  it('keeps that stance when another option changes, and drops the old key', async () => {
    const onChange = vi.fn()
    render(
      <StanceGroup
        label="Roles"
        terms={terms}
        value={[{ key: 'old', stance: 'preferred' }]}
        replacements={{ old: 'new' }}
        onChange={onChange}
        allowNoOpinion
      />,
    )
    const other = screen.getByRole('radiogroup', { name: 'Other family' })
    await userEvent.click(other.querySelector('input[value="rejected"]')!)
    expect(onChange).toHaveBeenCalledWith([
      { key: 'new', stance: 'preferred' },
      { key: 'other', stance: 'rejected' },
    ])
  })
})

describe('StanceGroup with an optional group (schedule, travel)', () => {
  const options = [
    { term_key: 'day', label: 'Day work' },
    { term_key: 'night', label: 'Night work' },
  ]

  it('shows terms the intent does not list as OK, without warning about an empty group', () => {
    render(<StanceGroup label="Schedule" terms={options} value={[]} onChange={vi.fn()} optional />)
    const night = screen.getByRole('radiogroup', { name: 'Night work' })
    expect(night.querySelector('input[value="acceptable"]')).toBeChecked()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.queryByRole('radio', { name: 'No opinion' })).not.toBeInTheDocument()
  })

  it('stores the choice made for one term', async () => {
    const onChange = vi.fn()
    render(<StanceGroup label="Schedule" terms={options} value={[]} onChange={onChange} optional />)
    const night = screen.getByRole('radiogroup', { name: 'Night work' })
    await userEvent.click(night.querySelector('input[value="rejected"]')!)
    expect(onChange).toHaveBeenCalledWith([{ key: 'night', stance: 'rejected' }])
  })

  it('still warns when every listed option is rejected', () => {
    render(
      <StanceGroup
        label="Schedule"
        terms={options}
        value={[
          { key: 'day', stance: 'rejected' },
          { key: 'night', stance: 'rejected' },
        ]}
        onChange={vi.fn()}
        optional
      />,
    )
    expect(screen.getByRole('alert')).toHaveTextContent(/at least one option/i)
  })
})
