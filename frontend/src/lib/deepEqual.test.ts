import { describe, expect, it } from 'vitest'
import { deepEqual } from './deepEqual'

describe('deepEqual', () => {
  it('compares nested values regardless of key order', () => {
    expect(deepEqual({ a: 1, b: { c: [1, 2] } }, { b: { c: [1, 2] }, a: 1 })).toBe(true)
  })
  it('detects differences in values, array order and length', () => {
    expect(deepEqual({ a: 1 }, { a: 2 })).toBe(false)
    expect(deepEqual([1, 2], [2, 1])).toBe(false)
    expect(deepEqual([1], [1, 2])).toBe(false)
    expect(deepEqual({ a: 1 }, { a: 1, b: 2 })).toBe(false)
  })
  it('distinguishes null, undefined-free primitives and types', () => {
    expect(deepEqual(null, null)).toBe(true)
    expect(deepEqual(null, 0)).toBe(false)
    expect(deepEqual('1', 1)).toBe(false)
    expect(deepEqual({ a: null }, { a: 0 })).toBe(false)
  })
})
