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
