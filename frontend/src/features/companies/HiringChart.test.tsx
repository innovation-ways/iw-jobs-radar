import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { HiringChart } from './HiringChart'

const weeks = [
  { week_start: '2026-09-14', new_offers: 0, open_offers: 2 },
  { week_start: '2026-09-21', new_offers: 1, open_offers: 3 },
  { week_start: '2026-09-28', new_offers: 4, open_offers: 6 },
]

describe('HiringChart', () => {
  it('explains what the bars are and gives the scale', () => {
    render(<HiringChart weeks={weeks} />)
    expect(screen.getByText(/each bar is one week/i)).toBeInTheDocument()
    // The vertical axis names its top value and zero; the horizontal axis its first and last week.
    const axis = screen.getByTestId('hiring-y-axis')
    expect(within(axis).getByText('4')).toBeInTheDocument()
    expect(within(axis).getByText('0')).toBeInTheDocument()
    expect(screen.getByText('14 Sep')).toBeInTheDocument()
    expect(screen.getByText('28 Sep')).toBeInTheDocument()
  })

  it('describes every bar in words, for hover, keyboard focus and screen readers', () => {
    render(<HiringChart weeks={weeks} />)
    const bar = screen.getByRole('img', {
      name: 'Week of 28 Sep: 4 new offers, 6 open at the end of the week',
    })
    expect(bar).toHaveAttribute('tabindex', '0')
    // The tooltip shows the same sentence.
    expect(within(bar).getByText('Week of 28 Sep')).toBeInTheDocument()
    expect(within(bar).getByText('4 new offers')).toBeInTheDocument()
    expect(within(bar).getByText('6 open at the end of the week')).toBeInTheDocument()
    expect(
      screen.getByRole('img', {
        name: 'Week of 21 Sep: 1 new offer, 3 open at the end of the week',
      }),
    ).toBeInTheDocument()
  })

  it('sizes the bars against the busiest week', () => {
    render(<HiringChart weeks={weeks} />)
    const bars = screen.getAllByTestId('hiring-bar')
    expect(bars.map((b) => b.style.height)).toEqual(['0%', '25%', '100%'])
  })

  it('says so when nothing new appeared', () => {
    render(<HiringChart weeks={weeks.map((w) => ({ ...w, new_offers: 0 }))} />)
    expect(screen.getByText(/no new offers in these 3 weeks/i)).toBeInTheDocument()
  })
})
