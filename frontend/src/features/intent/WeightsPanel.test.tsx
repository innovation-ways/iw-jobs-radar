import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { DEFAULT_WEIGHTS, type Weights } from './weights'
import { WeightsPanel } from './WeightsPanel'

function renderPanel(value: Weights = DEFAULT_WEIGHTS, onChange = vi.fn()) {
  render(<WeightsPanel value={value} onChange={onChange} />)
  return onChange
}

describe('WeightsPanel', () => {
  it('shows a slider per dimension with its share of the score', () => {
    renderPanel()
    const compensation = screen.getByRole('slider', { name: 'Compensation weight' })
    expect(compensation).toHaveValue('10')
    expect(compensation).toHaveAttribute('max', '40')
    const row = compensation.closest('[data-dimension]') as HTMLElement
    expect(within(row).getByText('10% of score')).toBeInTheDocument()
    expect(screen.getAllByRole('slider')).toHaveLength(12)
  })

  it('offers the career direction as an optional criterion that is off by default', () => {
    renderPanel()
    const slider = screen.getByRole('slider', { name: 'Career direction weight' })
    expect(slider).toHaveValue('0')
    const row = slider.closest('[data-dimension]') as HTMLElement
    expect(row).toHaveAttribute('data-excluded', 'true')
  })

  it('separates the optional criteria, which are off by default', () => {
    renderPanel()
    expect(screen.getByText(/optional criteria/i)).toBeInTheDocument()
    const optional = screen.getByRole('slider', { name: 'Qualifications weight' })
    expect(optional).toHaveValue('0')
    const row = optional.closest('[data-dimension]') as HTMLElement
    expect(within(row).getByText('Excluded from score')).toBeInTheDocument()
    expect(row).toHaveAttribute('data-excluded', 'true')
  })

  it('reports the new weights when a slider moves', () => {
    const onChange = renderPanel()
    fireEvent.change(screen.getByRole('slider', { name: 'Compensation weight' }), {
      target: { value: '30' },
    })
    expect(onChange).toHaveBeenCalledWith({ ...DEFAULT_WEIGHTS, compensation: 30 })
  })

  it('updates the shares when weights are not the defaults', () => {
    renderPanel({ ...DEFAULT_WEIGHTS, compensation: 30 })
    const row = screen
      .getByRole('slider', { name: 'Compensation weight' })
      .closest('[data-dimension]') as HTMLElement
    expect(within(row).getByText('25% of score')).toBeInTheDocument() // 30 of 120
  })

  it('describes each dimension on hover or focus', () => {
    renderPanel()
    const label = screen.getByText('Compensation', { selector: '[tabindex]' })
    expect(label).toHaveAttribute('tabindex', '0')
    expect(screen.getByRole('tooltip', { name: /compensation/i })).toHaveTextContent(
      /stated salary or day rate/i,
    )
  })

  it('shows the default and offers a reset only for changed weights', async () => {
    const onChange = renderPanel({ ...DEFAULT_WEIGHTS, compensation: 30 })
    const row = screen
      .getByRole('slider', { name: 'Compensation weight' })
      .closest('[data-dimension]') as HTMLElement
    expect(within(row).getByText(/default 10/i)).toBeInTheDocument()
    await userEvent.click(within(row).getByRole('button', { name: /reset compensation/i }))
    expect(onChange).toHaveBeenCalledWith({ ...DEFAULT_WEIGHTS, compensation: 10 })
    const untouched = screen
      .getByRole('slider', { name: 'Company profile weight' })
      .closest('[data-dimension]') as HTMLElement
    expect(within(untouched).queryByRole('button', { name: /reset/i })).not.toBeInTheDocument()
  })

  it('warns when every weight is zero', () => {
    const zero = Object.fromEntries(Object.keys(DEFAULT_WEIGHTS).map((k) => [k, 0])) as Weights
    renderPanel(zero)
    expect(screen.getByRole('alert')).toHaveTextContent(/at least one weight must be above 0/i)
    expect(screen.getAllByText('Excluded from score').length).toBeGreaterThan(0)
  })

  it('explains that existing scores are not changed, with the worked example', () => {
    renderPanel()
    expect(
      screen.getByText(/does not change scores that were already calculated/i),
    ).toBeInTheDocument()
    expect(screen.getByText(/82/)).toBeInTheDocument()
    expect(screen.getByText(/68/)).toBeInTheDocument()
  })

  it('resets everything to the defaults', async () => {
    const onChange = renderPanel({ ...DEFAULT_WEIGHTS, compensation: 30, qualifications: 5 })
    await userEvent.click(screen.getByRole('button', { name: /reset all weights/i }))
    expect(onChange).toHaveBeenCalledWith(DEFAULT_WEIGHTS)
  })
})
