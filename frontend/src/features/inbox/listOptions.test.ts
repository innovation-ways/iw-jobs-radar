import { describe, expect, it } from 'vitest'
import { DEFAULT_OPTIONS, hasActiveFilters, toQuery } from './listOptions'

const NOW = new Date('2026-10-09T12:00:00Z')

describe('list options', () => {
  it('sends only the sort by default', () => {
    expect(toQuery(DEFAULT_OPTIONS, NOW)).toEqual({ sort: 'fit_desc' })
    expect(hasActiveFilters(DEFAULT_OPTIONS)).toBe(false)
  })

  it('maps the fit presets to a minimum score or to jobs without a score', () => {
    expect(toQuery({ ...DEFAULT_OPTIONS, fit: '65' }, NOW)).toMatchObject({ fit_min: 65 })
    expect(toQuery({ ...DEFAULT_OPTIONS, fit: 'unscored' }, NOW)).toMatchObject({
      evaluated: false,
    })
    expect(toQuery({ ...DEFAULT_OPTIONS, fit: 'unscored' }, NOW)).not.toHaveProperty('fit_min')
  })

  it('turns "first seen within" into a lower bound counted from now', () => {
    expect(toQuery({ ...DEFAULT_OPTIONS, seen: '7d' }, NOW)).toMatchObject({
      from: '2026-10-02T12:00:00.000Z',
    })
    expect(toQuery({ ...DEFAULT_OPTIONS, seen: '24h' }, NOW)).toMatchObject({
      from: '2026-10-08T12:00:00.000Z',
    })
  })

  it('passes the chosen sort and reports active filters', () => {
    const options = { sort: 'newest', fit: '45', seen: '30d' } as const
    expect(toQuery(options, NOW).sort).toBe('newest')
    expect(hasActiveFilters(options)).toBe(true)
    expect(hasActiveFilters({ ...DEFAULT_OPTIONS, sort: 'oldest' })).toBe(false) // sort is not a filter
  })
})
