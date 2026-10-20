import { describe, expect, it } from 'vitest'
import { replacementsOf, resolveStances } from './merge'

describe('resolveStances', () => {
  const merged = { old: 'new' }

  it('gives a merged term’s stance to the term that replaced it', () => {
    expect(resolveStances([{ key: 'old', stance: 'preferred' }], merged)).toEqual([
      { key: 'new', stance: 'preferred' },
    ])
  })

  it('lets the surviving term’s own stance win', () => {
    expect(
      resolveStances(
        [
          { key: 'old', stance: 'preferred' },
          { key: 'new', stance: 'rejected' },
        ],
        merged,
      ),
    ).toEqual([{ key: 'new', stance: 'rejected' }])
  })

  it('leaves the list alone when nothing was merged', () => {
    const entries = [
      { key: 'a', stance: 'preferred' as const },
      { key: 'b', stance: 'rejected' as const },
    ]
    expect(resolveStances(entries, {})).toEqual(entries)
  })
})

describe('replacementsOf', () => {
  it('keeps the merges of one vocabulary', () => {
    const taxonomy = {
      groups: [],
      replacements: [
        { kind: 'sector', from_key: 'a', to_key: 'b' },
        { kind: 'role_family', from_key: 'c', to_key: 'd' },
      ],
    }
    expect(replacementsOf(taxonomy, 'sector')).toEqual({ a: 'b' })
    expect(replacementsOf({ groups: [] }, 'sector')).toEqual({})
  })
})
