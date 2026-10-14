import { describe, expect, it } from 'vitest'
import { summariseEngagement } from './engagement'

const DAY_RATE = {
  form: 'day_rate',
  currency: 'EUR',
  min: 450,
  max: 550,
  period: 'day',
  text: 'EUR 450-550 / day',
} as const

describe('summariseEngagement', () => {
  it('shows the kind and the stated day rate of a contract offer', () => {
    expect(summariseEngagement({ engagement_types: ['contractor_b2b'], pay: DAY_RATE })).toEqual({
      badges: ['Contractor (B2B)'],
      pay: 'EUR 450-550 / day',
      rateNotStated: false,
    })
  })

  it('says "Rate not stated" for a contract offer without pay', () => {
    expect(summariseEngagement({ engagement_types: ['contractor_agency'], pay: null })).toEqual({
      badges: ['Contract via agency'],
      pay: 'Rate not stated',
      rateNotStated: true,
    })
  })

  it('shows nothing about pay for a permanent or unknown offer without pay', () => {
    expect(summariseEngagement({ engagement_types: ['employee_permanent'], pay: null }).pay).toBe(
      null,
    )
    expect(summariseEngagement({ engagement_types: [], pay: null })).toEqual({
      badges: [],
      pay: null,
      rateNotStated: false,
    })
  })
})
