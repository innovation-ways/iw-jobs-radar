import { describe, expect, it } from 'vitest'
import {
  DEFAULT_WEIGHTS,
  DIMENSIONS,
  OPTIONAL_DIMENSIONS,
  effectiveShares,
  hasAnyWeight,
  scoreWith,
  type Weights,
} from './weights'

describe('weight dimensions', () => {
  it('lists the 8 active dimensions summing to 100 and 2 optional ones at 0', () => {
    expect(DIMENSIONS).toHaveLength(8)
    expect(OPTIONAL_DIMENSIONS).toHaveLength(2)
    const active = DIMENSIONS.reduce((sum, d) => sum + DEFAULT_WEIGHTS[d.key], 0)
    expect(active).toBe(100)
    for (const dimension of OPTIONAL_DIMENSIONS) expect(DEFAULT_WEIGHTS[dimension.key]).toBe(0)
  })

  it('describes every dimension in words', () => {
    for (const d of [...DIMENSIONS, ...OPTIONAL_DIMENSIONS]) {
      expect(d.label.length).toBeGreaterThan(3)
      expect(d.description.length).toBeGreaterThan(40)
    }
  })
})

describe('effective shares', () => {
  it('with the defaults each share equals its weight', () => {
    const shares = effectiveShares(DEFAULT_WEIGHTS)
    expect(shares.role_responsibilities).toBe(25)
    expect(shares.company_profile).toBe(7)
    expect(shares.qualifications).toBe(0)
  })

  it('shares always add up to 100 whatever the total', () => {
    const weights: Weights = { ...DEFAULT_WEIGHTS, compensation: 30, qualifications: 5 }
    const shares = effectiveShares(weights)
    const sum = (Object.values(shares) as number[]).reduce((a, b) => a + b, 0)
    expect(sum).toBeCloseTo(100, 6)
    expect(shares.compensation).toBeCloseTo((100 * 30) / 125, 6)
  })

  it('a zero weight is excluded (share 0) and does not dilute the others', () => {
    const weights: Weights = { ...DEFAULT_WEIGHTS, company_profile: 0 }
    const shares = effectiveShares(weights)
    expect(shares.company_profile).toBe(0)
    expect(shares.role_responsibilities).toBeCloseTo((100 * 25) / 93, 6)
  })

  it('has no shares when every weight is zero, and says so', () => {
    const zero = Object.fromEntries(Object.keys(DEFAULT_WEIGHTS).map((k) => [k, 0])) as Weights
    expect(hasAnyWeight(zero)).toBe(false)
    expect(effectiveShares(zero).role_responsibilities).toBeNull()
    expect(hasAnyWeight(DEFAULT_WEIGHTS)).toBe(true)
  })
})

describe('worked example of document 13 section 7', () => {
  const strengths = {
    role_responsibilities: 1,
    skills_technology: 0.8,
    work_arrangement_location: 1,
    engagement_terms: 1,
    compensation: null, // unknown contributes nothing
    seniority_experience: 1,
    domain_sector: 0.5,
    company_profile: 1,
    benefits_flexibility: null,
    qualifications: null,
  }

  it('scores 82 with the default weights', () => {
    expect(scoreWith(strengths, DEFAULT_WEIGHTS)).toBe(82)
  })

  it('scores 68 after raising compensation from 10 to 30 (weights sum 120)', () => {
    expect(scoreWith(strengths, { ...DEFAULT_WEIGHTS, compensation: 30 })).toBe(68)
  })

  it('has no score without any weight', () => {
    const zero = Object.fromEntries(Object.keys(DEFAULT_WEIGHTS).map((k) => [k, 0])) as Weights
    expect(scoreWith(strengths, zero)).toBeNull()
  })
})
