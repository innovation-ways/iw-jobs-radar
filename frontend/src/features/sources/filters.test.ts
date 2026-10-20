import { describe, expect, it } from 'vitest'
import { DEFAULT_FILTERS, filtersProblem } from './filters'

describe('filtersProblem', () => {
  it('asks for an area when some are offered', () => {
    expect(filtersProblem({ ...DEFAULT_FILTERS, categories: [] })).toMatch(
      /choose at least one area of work/i,
    )
    expect(filtersProblem({ ...DEFAULT_FILTERS, categories: ['electrical'] })).toBeNull()
  })

  it('does not ask for one when none is offered (no pack is on)', () => {
    expect(filtersProblem({ ...DEFAULT_FILTERS, categories: [] }, false)).toBeNull()
  })

  it('starts with no area chosen: the screens fill in the owner’s areas', () => {
    expect(DEFAULT_FILTERS.categories).toEqual([])
  })

  it('still checks the age and the limit', () => {
    expect(filtersProblem({ ...DEFAULT_FILTERS, max_age_days: 0 }, false)).toMatch(/1 to 365/)
    expect(filtersProblem({ ...DEFAULT_FILTERS, max_postings_per_run: 9999 }, false)).toMatch(
      /5,000/,
    )
  })
})
