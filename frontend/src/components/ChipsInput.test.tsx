import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ChipsInput } from './ChipsInput'

describe('ChipsInput', () => {
  it('lists values and removes one with its button', async () => {
    const onChange = vi.fn()
    render(<ChipsInput label="Regions" values={['EU', 'UK']} onChange={onChange} />)
    expect(screen.getByText('EU')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Remove EU' }))
    expect(onChange).toHaveBeenCalledWith(['UK'])
  })

  it('adds a value on Enter or comma and clears the field', async () => {
    const onChange = vi.fn()
    render(<ChipsInput label="Words" values={['unpaid']} onChange={onChange} />)
    const input = screen.getByLabelText('Words')
    await userEvent.type(input, 'internship{Enter}')
    expect(onChange).toHaveBeenLastCalledWith(['unpaid', 'internship'])
    await userEvent.type(input, 'volunteer,')
    expect(onChange).toHaveBeenLastCalledWith(['unpaid', 'volunteer'])
    expect(input).toHaveValue('')
  })

  it('ignores blanks and duplicates (case-insensitive)', async () => {
    const onChange = vi.fn()
    render(<ChipsInput label="Words" values={['Unpaid']} onChange={onChange} />)
    const input = screen.getByLabelText('Words')
    await userEvent.type(input, '   {Enter}')
    await userEvent.type(input, 'unpaid{Enter}')
    expect(onChange).not.toHaveBeenCalled()
  })

  it('normalises and validates what is added', async () => {
    const onChange = vi.fn()
    render(
      <ChipsInput
        label="Regions"
        values={[]}
        onChange={onChange}
        normalise={(value) => value.toUpperCase()}
        validate={(value) =>
          /^[A-Z]{2,6}$/.test(value) ? null : 'Use a country code or EU, UK, EEA.'
        }
      />,
    )
    const input = screen.getByLabelText('Regions')
    await userEvent.type(input, 'eu{Enter}')
    expect(onChange).toHaveBeenCalledWith(['EU'])
    await userEvent.type(input, 'not valid!{Enter}')
    expect(screen.getByRole('alert')).toHaveTextContent('Use a country code')
    expect(onChange).toHaveBeenCalledTimes(1)
  })

  it('adds a pending value when the field loses focus', async () => {
    const onChange = vi.fn()
    render(<ChipsInput label="Words" values={[]} onChange={onChange} />)
    await userEvent.type(screen.getByLabelText('Words'), 'scam')
    await userEvent.tab()
    expect(onChange).toHaveBeenCalledWith(['scam'])
  })
})
