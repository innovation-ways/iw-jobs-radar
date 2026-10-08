import { describe, expect, it } from 'vitest'
import { TAXONOMY, makeProfile } from '@/test/builders'
import { defaultIntentDefinition } from './defaults'
import { intentProblem } from './validate'

const base = () => defaultIntentDefinition(TAXONOMY, makeProfile())

describe('intentProblem', () => {
  it('accepts the default intent', () => {
    expect(intentProblem(base())).toBeNull()
  })

  it('requires a name', () => {
    expect(intentProblem({ ...base(), title: '   ' })).toMatch(/name/i)
  })

  it.each([
    'role_families',
    'work_arrangements',
    'engagement_types',
    'seniority_levels',
    'employer_types',
  ] as const)('refuses a %s group where everything is rejected', (group) => {
    const intent = base()
    intent.stances[group] = intent.stances[group].map((entry) => ({
      ...entry,
      stance: 'rejected' as const,
    }))
    expect(intentProblem(intent)).toMatch(/not be rejected/i)
  })

  it('allows no sector opinion but not only rejected sectors', () => {
    const intent = base()
    intent.stances.sectors = [{ key: 'gambling', stance: 'rejected' }]
    expect(intentProblem(intent)).toMatch(/sectors/i)
    intent.stances.sectors = []
    expect(intentProblem(intent)).toBeNull()
  })

  it('needs at least one remote region and one language', () => {
    const intent = base()
    intent.work_rules.remote.eligible_regions = []
    expect(intentProblem(intent)).toMatch(/region/i)
    const noLanguage = base()
    noLanguage.languages.can_work_in = []
    expect(intentProblem(noLanguage)).toMatch(/language/i)
  })

  it('needs at least one weight above zero', () => {
    const intent = base()
    for (const key of Object.keys(intent.weights) as (keyof typeof intent.weights)[])
      intent.weights[key] = 0
    expect(intentProblem(intent)).toMatch(/weight/i)
  })

  it('checks pay targets against minimums', () => {
    const intent = base()
    intent.compensation.employee_pay = {
      currency: 'EUR',
      payments_per_year: 14,
      annual_minimum: 60000,
      annual_target: 50000,
    }
    expect(intentProblem(intent)).toMatch(/pay/i)
    intent.compensation.employee_pay = null
    intent.compensation.contractor_day_rate = { currency: 'EUR', minimum: 500, target: 400 }
    expect(intentProblem(intent)).toMatch(/day rate/i)
  })

  it('keeps the hybrid radius within 1 to 500 km', () => {
    const intent = base()
    intent.work_rules.onsite_hybrid.radius_km = 0
    expect(intentProblem(intent)).toMatch(/distance/i)
    intent.work_rules.onsite_hybrid.radius_km = 501
    expect(intentProblem(intent)).toMatch(/distance/i)
  })
})
