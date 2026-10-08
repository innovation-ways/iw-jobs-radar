import { describe, expect, it } from 'vitest'
import { bandOf, NOT_EVALUATED } from './bands'

describe('bandOf', () => {
  it.each([
    ['excellent', 'Excellent fit', 'Excellent', 'good'],
    ['strong', 'Strong fit', 'Strong', 'good'],
    ['average', 'Average fit', 'Average', 'caution'],
    ['low', 'Low fit', 'Low', 'neutral'],
    ['not_recommended', 'Not recommended', 'Not rec.', 'bad'],
  ] as const)('%s', (band, label, short, tone) => {
    expect(bandOf(band)).toMatchObject({ label, short, tone })
  })

  it('has a distinct description for jobs that were not evaluated', () => {
    expect(NOT_EVALUATED.label).toBe('Not evaluated')
    expect(NOT_EVALUATED.tone).toBe('neutral')
  })
})
