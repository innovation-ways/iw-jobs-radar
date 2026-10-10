import type { components } from '@/api/schema'

export type Weights = components['schemas']['Weights']
export type WeightKey = keyof Weights

export interface Dimension {
  key: WeightKey
  label: string
  description: string
}

/** The eight dimensions that make up the fit score by default (document 13, section 7). */
export const DIMENSIONS: Dimension[] = [
  {
    key: 'role_responsibilities',
    label: 'Role & responsibilities',
    description:
      "How well the job's role and day-to-day responsibilities match the role families you prefer. A role family you marked Reject rules the job out.",
  },
  {
    key: 'skills_technology',
    label: 'Skills & technology',
    description:
      'Overlap between the skills and technologies the posting asks for and those in your profile. The technology stack is a frequent deal-breaker for developers.',
  },
  {
    key: 'work_arrangement_location',
    label: 'Work arrangement & location',
    description:
      'Remote, hybrid or on-site, and whether the place fits: eligible regions and time zone for remote work, distance from your base for hybrid or on-site. An arrangement you marked Reject rules the job out.',
  },
  {
    key: 'engagement_terms',
    label: 'Engagement & contract terms',
    description:
      'Employment type and terms (contract, freelance, permanent, part-time) compared with what you prefer. Types you marked Reject rule the job out.',
  },
  {
    key: 'compensation',
    label: 'Compensation',
    description:
      'The stated salary or day rate compared with your expectation, using the right form (annual salary or day rate). If pay is not stated it is unknown and adds nothing.',
  },
  {
    key: 'seniority_experience',
    label: 'Seniority & experience',
    description:
      'Whether the level the job asks for matches your experience and the levels you prefer.',
  },
  {
    key: 'domain_sector',
    label: 'Domain & sector',
    description:
      'The industry or domain of the employer and product compared with the sectors you prefer, accept or reject.',
  },
  {
    key: 'company_profile',
    label: 'Company profile',
    description:
      'Employer type (direct employer, agency), size and how clearly the company and role are described.',
  },
]

/** Optional criteria: off (weight 0) by default because postings state them inconsistently. */
export const OPTIONAL_DIMENSIONS: Dimension[] = [
  {
    key: 'benefits_flexibility',
    label: 'Benefits & flexibility',
    description:
      'Optional. Benefits and flexibility the posting mentions, such as equity, learning budget, four-day week or flexible hours. Off by default because postings state them inconsistently.',
  },
  {
    key: 'qualifications',
    label: 'Qualifications',
    description:
      'Optional. Education or certifications the posting asks for compared with yours. Off by default.',
  },
  {
    key: 'career_direction',
    label: 'Career direction',
    description:
      'Optional. How well the job fits the directions you wrote in your profile, judged by the local model for jobs first seen after you added them. The best fit among your directions counts; a job that has not been assessed is left out instead of counting as zero. Off by default.',
  },
]

export const DEFAULT_WEIGHTS: Weights = {
  role_responsibilities: 25,
  skills_technology: 15,
  work_arrangement_location: 15,
  engagement_terms: 10,
  compensation: 10,
  seniority_experience: 8,
  domain_sector: 10,
  company_profile: 7,
  benefits_flexibility: 0,
  qualifications: 0,
  career_direction: 0,
}

export const MAX_WEIGHT = 40

const KEYS = Object.keys(DEFAULT_WEIGHTS) as WeightKey[]

function total(weights: Weights): number {
  return KEYS.reduce((sum, key) => sum + weights[key], 0)
}

/** At least one weight must be above 0, otherwise there is nothing to score. */
export function hasAnyWeight(weights: Weights): boolean {
  return total(weights) > 0
}

/**
 * Each dimension's share of the final score in percent. Weights are relative, so a share is
 * `100 * weight / sum of weights`; a zero weight is excluded (0). `null` when every weight is 0.
 */
export function effectiveShares(weights: Weights): Record<WeightKey, number | null> {
  const sum = total(weights)
  return Object.fromEntries(
    KEYS.map((key) => [key, sum === 0 ? null : (100 * weights[key]) / sum]),
  ) as Record<WeightKey, number | null>
}

/**
 * The matching-v1 score for one job: `100 * sum(weight * strength) / sum(weights)`, where an
 * unknown strength (`null`) contributes nothing but its weight still counts (document 13, 7).
 * Used for the worked example; real scores are computed by the backend from stored judgements.
 */
export function scoreWith(
  strengths: Record<WeightKey, number | null>,
  weights: Weights,
): number | null {
  const sum = total(weights)
  if (sum === 0) return null
  const earned = KEYS.reduce((acc, key) => acc + weights[key] * (strengths[key] ?? 0), 0)
  return Math.round((100 * earned) / sum)
}
