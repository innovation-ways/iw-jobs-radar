import type { InboxItem } from './queries'

/** Readable names of the engagement types the API returns (taxonomy keys; ADR-073). */
export const ENGAGEMENT_LABELS: Record<string, string> = {
  employee_permanent: 'Permanent',
  employee_fixed_term: 'Fixed term',
  contractor_b2b: 'Contractor (B2B)',
  freelance: 'Freelance',
  contractor_agency: 'Contract via agency',
  internship: 'Internship',
}

/** Engagement types of self-employed or agency contract work. */
export const CONTRACT_KINDS = ['contractor_b2b', 'freelance', 'contractor_agency'] as const

/** What the card shows about the contract: kind badges and the pay line. */
export interface EngagementSummary {
  /** Readable engagement kinds, in the order the posting states them. */
  badges: string[]
  /** The stated pay (``EUR 450-550 / day``), or "Rate not stated" for a contract offer without one. */
  pay: string | null
  /** True when the offer is contract work and the posting states no pay. */
  rateNotStated: boolean
}

/** Summarise an inbox item's engagement kinds and pay for its card. Nothing is converted. */
export function summariseEngagement(
  item: Pick<InboxItem, 'engagement_types' | 'pay'>,
): EngagementSummary {
  const kinds = item.engagement_types
  const isContract = kinds.some((kind) => (CONTRACT_KINDS as readonly string[]).includes(kind))
  const rateNotStated = isContract && item.pay === null
  return {
    badges: kinds.map((kind) => ENGAGEMENT_LABELS[kind] ?? kind),
    pay: item.pay?.text ?? (rateNotStated ? 'Rate not stated' : null),
    rateNotStated,
  }
}
