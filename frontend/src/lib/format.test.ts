import { describe, expect, it } from 'vitest'
import { formatAge } from './format'

const NOW = new Date('2026-10-08T12:00:00Z')

describe('formatAge', () => {
  it.each([
    ['2026-10-08T11:59:30Z', 'just now'],
    ['2026-10-08T11:30:00Z', '30m'],
    ['2026-10-08T10:00:00Z', '2h'],
    ['2026-10-07T12:00:00Z', '1d'],
    ['2026-10-01T12:00:00Z', '7d'],
    ['2026-09-17T12:00:00Z', '3w'],
    ['2026-07-08T12:00:00Z', '3mo'],
    ['2024-10-08T12:00:00Z', '2y'],
  ])('%s is %s', (iso, expected) => {
    expect(formatAge(iso, NOW)).toBe(expected)
  })

  it('never shows a negative age (clocks drift)', () => {
    expect(formatAge('2026-10-08T12:05:00Z', NOW)).toBe('just now')
  })
})
