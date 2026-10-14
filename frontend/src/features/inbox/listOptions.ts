/** How the inbox list is ordered and narrowed, and how that becomes API query parameters. */

export type SortKey = 'fit_desc' | 'newest' | 'oldest'
export type FitFilter = 'any' | '80' | '65' | '45' | 'unscored'
export type SeenFilter = 'any' | '24h' | '7d' | '30d'
/** Kind of work contract (ADR-073); ``contract`` is B2B, freelance and agency together. */
export type ContractFilter =
  'any' | 'contract' | 'b2b' | 'freelance' | 'agency' | 'permanent' | 'fixed_term' | 'unknown'
export type RateFilter = 'any' | 'stated' | 'not_stated'

export interface ListOptions {
  sort: SortKey
  fit: FitFilter
  seen: SeenFilter
  contract: ContractFilter
  rate: RateFilter
}

export const DEFAULT_OPTIONS: ListOptions = {
  sort: 'fit_desc',
  fit: 'any',
  seen: 'any',
  contract: 'any',
  rate: 'any',
}

export const SORT_LABELS: Record<SortKey, string> = {
  fit_desc: 'Best fit',
  newest: 'Newest first seen',
  oldest: 'Oldest first seen',
}

/** Fit presets follow the bands of matching-v1 (80 excellent, 65 strong, 45 average). */
export const FIT_LABELS: Record<FitFilter, string> = {
  any: 'Any fit',
  '80': 'Excellent (80+)',
  '65': 'Strong or better (65+)',
  '45': 'Average or better (45+)',
  unscored: 'Not evaluated',
}

export const SEEN_LABELS: Record<SeenFilter, string> = {
  any: 'Any time',
  '24h': 'Last 24 hours',
  '7d': 'Last 7 days',
  '30d': 'Last 30 days',
}

export const CONTRACT_LABELS: Record<ContractFilter, string> = {
  any: 'Any contract type',
  contract: 'Contract work (all kinds)',
  b2b: 'Contractor (B2B)',
  freelance: 'Freelance',
  agency: 'Contract via agency',
  permanent: 'Permanent employee',
  fixed_term: 'Fixed-term employee',
  unknown: 'Not stated',
}

export const RATE_LABELS: Record<RateFilter, string> = {
  any: 'Any rate',
  stated: 'Rate stated',
  not_stated: 'Rate not stated',
}

/** The engagement type keys each contract preset asks the API for. */
const ENGAGEMENT_KEYS: Record<Exclude<ContractFilter, 'any'>, string[]> = {
  contract: ['contractor_b2b', 'freelance', 'contractor_agency'],
  b2b: ['contractor_b2b'],
  freelance: ['freelance'],
  agency: ['contractor_agency'],
  permanent: ['employee_permanent'],
  fixed_term: ['employee_fixed_term'],
  unknown: ['unknown'],
}

const SEEN_MS: Record<Exclude<SeenFilter, 'any'>, number> = {
  '24h': 24 * 3600_000,
  '7d': 7 * 24 * 3600_000,
  '30d': 30 * 24 * 3600_000,
}

/** Query parameters of `GET /inbox` for these options; ``now`` anchors "first seen within". */
export function toQuery(
  options: ListOptions,
  now: Date,
): Record<string, string | number | boolean | string[]> {
  const query: Record<string, string | number | boolean | string[]> = { sort: options.sort }
  if (options.contract !== 'any') query.engagement = ENGAGEMENT_KEYS[options.contract]
  if (options.rate !== 'any') query.rate = options.rate
  if (options.fit === 'unscored') query.evaluated = false
  else if (options.fit !== 'any') query.fit_min = Number(options.fit)
  if (options.seen !== 'any') {
    query.from = new Date(now.getTime() - SEEN_MS[options.seen]).toISOString()
  }
  return query
}

/** True when a filter (not the sort order) narrows the list. */
export function hasActiveFilters(options: ListOptions): boolean {
  return (
    options.fit !== 'any' ||
    options.seen !== 'any' ||
    options.contract !== 'any' ||
    options.rate !== 'any'
  )
}

const SORTS = Object.keys(SORT_LABELS) as SortKey[]

/** A stored sort key, or the default when it is missing or no longer valid. */
export function parseSort(value: string | null): SortKey {
  return SORTS.find((key) => key === value) ?? DEFAULT_OPTIONS.sort
}

/** A fit filter taken from a link such as ``/inbox?fit=unscored``; unknown values are ignored. */
export function parseFit(value: string | null): FitFilter {
  return (Object.keys(FIT_LABELS) as FitFilter[]).find((key) => key === value) ?? 'any'
}

/** A contract filter taken from a link such as ``/inbox?contract=contract``; unknown values are ignored. */
export function parseContract(value: string | null): ContractFilter {
  return (Object.keys(CONTRACT_LABELS) as ContractFilter[]).find((key) => key === value) ?? 'any'
}

/** A rate filter taken from a link such as ``/inbox?rate=stated``; unknown values are ignored. */
export function parseRate(value: string | null): RateFilter {
  return (Object.keys(RATE_LABELS) as RateFilter[]).find((key) => key === value) ?? 'any'
}
