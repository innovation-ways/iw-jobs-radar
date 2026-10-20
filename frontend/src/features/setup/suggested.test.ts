import { describe, expect, it } from 'vitest'
import { TAXONOMY, makeProfile } from '@/test/builders'
import { defaultIntentDefinition } from '@/features/intent/defaults'
import { DEFAULT_WEIGHTS } from '@/features/intent/weights'
import { applyPackDefaults, type IntentDefaults } from './suggested'

const base = () => defaultIntentDefinition(TAXONOMY, makeProfile())

const trades: IntentDefaults = {
  pack_key: 'construction_trades',
  work_arrangements: { onsite: 'preferred', remote: 'rejected' },
  schedules: { day: 'preferred', night: 'acceptable' },
  travel_levels: { frequent: 'rejected' },
  weights: { ...DEFAULT_WEIGHTS, qualifications: 12, schedule_travel: 8, compensation: 10 },
  reject_missing_credentials: true,
}

describe('applyPackDefaults', () => {
  it('sets the stances the pack suggests and leaves the other options as they were', () => {
    const result = applyPackDefaults(base(), trades)
    expect(result.stances.work_arrangements).toEqual([
      { key: 'remote', stance: 'rejected' },
      { key: 'hybrid', stance: 'acceptable' },
      { key: 'onsite', stance: 'preferred' },
    ])
    expect(result.stances.schedules).toEqual([
      { key: 'day', stance: 'preferred' },
      { key: 'night', stance: 'acceptable' },
    ])
    expect(result.stances.travel_levels).toEqual([
      { key: 'none', stance: 'acceptable' },
      { key: 'frequent', stance: 'rejected' },
    ])
  })

  it('takes the pack’s weights and the credential option', () => {
    const result = applyPackDefaults(base(), trades)
    expect(result.weights.qualifications).toBe(12)
    expect(result.weights.schedule_travel).toBe(8)
    expect(result.filters.reject_missing_credentials).toBe(true)
  })

  it('changes nothing when no pack suggests anything', () => {
    const empty: IntentDefaults = {
      pack_key: null,
      work_arrangements: {},
      schedules: {},
      travel_levels: {},
      weights: { ...DEFAULT_WEIGHTS },
      reject_missing_credentials: false,
    }
    expect(applyPackDefaults(base(), empty)).toEqual(base())
  })

  it('does not reject every option of a group even if a pack asked for it', () => {
    const everything: IntentDefaults = {
      ...trades,
      work_arrangements: { onsite: 'rejected', remote: 'rejected', hybrid: 'rejected' },
    }
    const stances = applyPackDefaults(base(), everything).stances.work_arrangements
    expect(stances.some((s) => s.stance !== 'rejected')).toBe(true)
  })
})
