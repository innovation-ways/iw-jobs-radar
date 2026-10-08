import { describe, expect, it } from 'vitest'
import { cardSignals, signalIcon } from './signals'

type Signal = Parameters<typeof cardSignals>[0][number]
const s = (
  key: string,
  status: Signal['status'],
  quality: Signal['quality'] = null,
  excluded = false,
): Signal => ({
  dimension_key: key,
  status,
  quality,
  excluded,
})

describe('signalIcon', () => {
  it('maps status and quality to a symbol and words', () => {
    expect(signalIcon(s('x', 'match', 'strong'))).toEqual({ symbol: '✓', word: 'match' })
    expect(signalIcon(s('x', 'match', 'partial'))).toEqual({ symbol: '~', word: 'partial match' })
    expect(signalIcon(s('x', 'match', 'weak'))).toEqual({ symbol: '~', word: 'partial match' })
    expect(signalIcon(s('x', 'mismatch'))).toEqual({ symbol: '✕', word: 'mismatch' })
    expect(signalIcon(s('x', 'unknown'))).toEqual({ symbol: '?', word: 'unknown' })
  })
})

describe('cardSignals', () => {
  const all = [
    s('role_responsibilities', 'match', 'strong'),
    s('skills_technology', 'match', 'partial'),
    s('work_arrangement_location', 'match', 'strong'),
    s('engagement_terms', 'mismatch'),
    s('compensation', 'unknown'),
    s('seniority_experience', 'match', 'strong'),
    s('domain_sector', 'match', 'partial'),
    s('company_profile', 'unknown'),
    s('benefits_flexibility', 'unknown', null, true),
    s('qualifications', 'unknown', null, true),
  ]

  it('shows the four facts that usually decide look-or-skip, in a fixed order, with labels', () => {
    expect(cardSignals(all).map((c) => c.label)).toEqual(['Work', 'Engagement', 'Pay', 'Skills'])
  })

  it('carries each signal status with its icon', () => {
    const [work, engagement, pay] = cardSignals(all)
    expect(work).toMatchObject({ symbol: '✓', word: 'match' })
    expect(engagement).toMatchObject({ symbol: '✕', word: 'mismatch' })
    expect(pay).toMatchObject({ symbol: '?', word: 'unknown' })
  })

  it('skips dimensions that are excluded and ones that are missing', () => {
    const only = [s('compensation', 'unknown'), s('skills_technology', 'match', 'strong', true)]
    expect(cardSignals(only).map((c) => c.label)).toEqual(['Pay'])
    expect(cardSignals([])).toEqual([])
  })
})
