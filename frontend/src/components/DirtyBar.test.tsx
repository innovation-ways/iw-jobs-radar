import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { DirtyBar } from './DirtyBar'

describe('DirtyBar', () => {
  it('is not shown while nothing changed', () => {
    render(<DirtyBar dirty={false} saving={false} onSave={vi.fn()} onDiscard={vi.fn()} />)
    expect(screen.queryByRole('region', { name: /unsaved/i })).not.toBeInTheDocument()
  })

  it('offers Save and Discard and passes the optional change note', async () => {
    const onSave = vi.fn()
    const onDiscard = vi.fn()
    render(<DirtyBar dirty saving={false} onSave={onSave} onDiscard={onDiscard} />)
    expect(screen.getByRole('region', { name: /unsaved/i })).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText(/change note/i), 'More pay')
    await userEvent.click(screen.getByRole('button', { name: /save revision/i }))
    expect(onSave).toHaveBeenCalledWith('More pay')
    await userEvent.click(screen.getByRole('button', { name: /discard/i }))
    expect(onDiscard).toHaveBeenCalled()
  })

  it('disables saving while saving or when the draft is invalid and says why', () => {
    const { rerender } = render(<DirtyBar dirty saving onSave={vi.fn()} onDiscard={vi.fn()} />)
    expect(screen.getByRole('button', { name: /saving/i })).toBeDisabled()
    rerender(
      <DirtyBar
        dirty
        saving={false}
        problem="Headline is required."
        onSave={vi.fn()}
        onDiscard={vi.fn()}
      />,
    )
    expect(screen.getByRole('button', { name: /save revision/i })).toBeDisabled()
    expect(screen.getByText('Headline is required.')).toBeInTheDocument()
  })

  it('shows a save error', () => {
    render(
      <DirtyBar
        dirty
        saving={false}
        error="The profile changed since it was loaded."
        onSave={vi.fn()}
        onDiscard={vi.fn()}
      />,
    )
    expect(screen.getByRole('alert')).toHaveTextContent(/changed since/i)
  })
})
