import { describe, expect, it } from 'vitest'
import { TAXONOMY, makeProfile } from '@/test/builders'
import { defaultIntentDefinition } from './defaults'
import { DEFAULT_WEIGHTS } from './weights'

describe('defaultIntentDefinition', () => {
  const definition = defaultIntentDefinition(TAXONOMY, makeProfile())

  it('lists every term of the closed groups as acceptable', () => {
    expect(definition.stances.work_arrangements).toEqual([
      { key: 'remote', stance: 'acceptable' },
      { key: 'hybrid', stance: 'acceptable' },
      { key: 'onsite', stance: 'acceptable' },
    ])
    expect(definition.stances.employer_types.map((e) => e.key)).toEqual([
      'direct_employer',
      'agency',
    ])
    expect(definition.stances.engagement_types).toHaveLength(2)
    expect(definition.stances.seniority_levels).toHaveLength(2)
  })

  it('lists every working pattern and travel level as acceptable', () => {
    expect(definition.stances.schedules).toEqual([
      { key: 'day', stance: 'acceptable' },
      { key: 'night', stance: 'acceptable' },
    ])
    expect(definition.stances.travel_levels).toEqual([
      { key: 'none', stance: 'acceptable' },
      { key: 'frequent', stance: 'acceptable' },
    ])
  })

  it('starts with every role family acceptable (the group may not be empty) and no sector opinion', () => {
    expect(definition.stances.role_families.map((r) => r.stance)).toEqual([
      'acceptable',
      'acceptable',
    ])
    expect(definition.stances.sectors).toEqual([])
  })

  it('takes the base place, time zone and languages from the profile', () => {
    expect(definition.work_rules.onsite_hybrid).toMatchObject({
      base_place: 'Lisbon, Portugal',
      latitude: 38.72,
      longitude: -9.14,
      radius_km: 40,
    })
    expect(definition.work_rules.remote.timezone).toBe('Europe/Lisbon')
    expect(definition.languages.can_work_in).toEqual(['pt'])
  })

  it('uses the default weights, threshold and no pay expectations', () => {
    expect(definition.weights).toEqual(DEFAULT_WEIGHTS)
    expect(definition.alert_threshold).toBe(65)
    expect(definition.compensation.employee_pay).toBeNull()
    expect(definition.compensation.contractor_day_rate).toBeNull()
  })

  it('still works for a profile without a revision', () => {
    const blank = defaultIntentDefinition(TAXONOMY, makeProfile({}, 0))
    expect(blank.work_rules.remote.timezone).toBe('UTC')
    expect(blank.languages.can_work_in).toEqual(['en'])
    expect(blank.work_rules.onsite_hybrid.base_place).toBeTruthy()
  })
})
