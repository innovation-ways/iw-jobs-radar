import { describe, expect, it } from 'vitest'
import { diffRevisions } from './diff'

describe('diffRevisions', () => {
  it('reports nothing for identical content', () => {
    expect(diffRevisions({ a: 1, b: { c: [1, 2] } }, { b: { c: [1, 2] }, a: 1 })).toEqual([])
  })

  it('reports changed values with their path', () => {
    expect(
      diffRevisions(
        { weights: { compensation: 10, role: 25 } },
        { weights: { compensation: 30, role: 25 } },
      ),
    ).toEqual([{ path: 'weights › compensation', kind: 'changed', before: '10', after: '30' }])
  })

  it('reports list items that were added or removed by their name', () => {
    const before = {
      skills: [
        { name: 'Python', years: 10 },
        { name: 'Kubernetes', years: 4 },
      ],
    }
    const after = {
      skills: [
        { name: 'Python', years: 10 },
        { name: 'Rust', years: 1 },
      ],
    }
    expect(diffRevisions(before, after)).toEqual([
      { path: 'skills', kind: 'removed', before: 'Kubernetes', after: null },
      { path: 'skills', kind: 'added', before: null, after: 'Rust' },
    ])
  })

  it('reports lists of plain values', () => {
    expect(diffRevisions({ keywords: ['llm', 'rag'] }, { keywords: ['llm', 'billing'] })).toEqual([
      { path: 'keywords', kind: 'removed', before: 'rag', after: null },
      { path: 'keywords', kind: 'added', before: null, after: 'billing' },
    ])
  })

  it('labels stance entries by key and stance', () => {
    const before = { stances: { sectors: [{ key: 'telecom', stance: 'preferred' }] } }
    const after = { stances: { sectors: [{ key: 'telecom', stance: 'rejected' }] } }
    expect(diffRevisions(before, after)).toEqual([
      { path: 'stances › sectors', kind: 'removed', before: 'telecom: preferred', after: null },
      { path: 'stances › sectors', kind: 'added', before: null, after: 'telecom: rejected' },
    ])
  })

  it('reports a value that appears or disappears', () => {
    expect(diffRevisions({ a: null }, { a: 5 })).toEqual([
      { path: 'a', kind: 'changed', before: 'not set', after: '5' },
    ])
    expect(diffRevisions({ a: 1 }, { a: 1, b: 'x' })).toEqual([
      { path: 'b', kind: 'changed', before: 'not set', after: 'x' },
    ])
  })

  it('ignores the provenance of facts', () => {
    const before = { skills: [{ name: 'Python', provenance: { accepted_at: '2026-01-01' } }] }
    const after = { skills: [{ name: 'Python', provenance: { accepted_at: '2026-02-02' } }] }
    expect(diffRevisions(before, after)).toEqual([])
  })
})
