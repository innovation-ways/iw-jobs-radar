import type { IntentDefinition } from '@/features/profile/queries'
import { hasAnyWeight } from './weights'

const REQUIRED_GROUPS = [
  ['role_families', 'Roles'],
  ['work_arrangements', 'Work arrangement'],
  ['engagement_types', 'Engagement'],
  ['seniority_levels', 'Seniority'],
  ['employer_types', 'Employer'],
] as const

/**
 * The first reason this draft cannot be saved, or `null`. It mirrors the server rules so the owner
 * gets immediate feedback; the server remains the authority and answers 422 for anything else.
 */
export function intentProblem(intent: IntentDefinition): string | null {
  if (!intent.title.trim()) return 'Give the intent a name.'
  for (const [group, label] of REQUIRED_GROUPS) {
    const entries = intent.stances[group]
    if (!entries.some((entry) => entry.stance !== 'rejected')) {
      return `${label}: at least one option must not be rejected.`
    }
  }
  const sectors = intent.stances.sectors ?? []
  if (sectors.length > 0 && !sectors.some((entry) => entry.stance !== 'rejected')) {
    return 'Sectors: at least one option must not be rejected (or leave sectors without opinion).'
  }
  if (intent.work_rules.remote.eligible_regions.length === 0) {
    return 'Add at least one region you can work remotely from.'
  }
  const radius = intent.work_rules.onsite_hybrid.radius_km
  if (!Number.isInteger(radius) || radius < 1 || radius > 500) {
    return 'The hybrid and on-site distance must be between 1 and 500 km.'
  }
  const employee = intent.compensation.employee_pay
  if (employee && employee.annual_target < employee.annual_minimum) {
    return 'Employee pay: the target must not be below the minimum.'
  }
  const contractor = intent.compensation.contractor_day_rate
  if (contractor && contractor.target < contractor.minimum) {
    return 'Day rate: the target must not be below the minimum.'
  }
  if (intent.languages.can_work_in.length === 0) return 'Add at least one working language.'
  if (!hasAnyWeight(intent.weights)) return 'At least one weight must be above 0.'
  return null
}
