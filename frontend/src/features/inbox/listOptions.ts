/** How the inbox list is ordered and narrowed, and how that becomes API query parameters. */

export type SortKey = 'fit_desc' | 'newest' | 'oldest'
export type FitFilter = 'any' | '80' | '65' | '45' | 'unscored'
export type SeenFilter = 'any' | '24h' | '7d' | '30d'

export interface ListOptions {
  sort: SortKey
  fit: FitFilter
  seen: SeenFilter
}

export const DEFAULT_OPTIONS: ListOptions = { sort: 'fit_desc', fit: 'any', seen: 'any' }

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

const SEEN_MS: Record<Exclude<SeenFilter, 'any'>, number> = {
  '24h': 24 * 3600_000,
  '7d': 7 * 24 * 3600_000,
  '30d': 30 * 24 * 3600_000,
}

/** Query parameters of `GET /inbox` for these options; ``now`` anchors "first seen within". */
export function toQuery(
  options: ListOptions,
  now: Date,
): Record<string, string | number | boolean> {
  const query: Record<string, string | number | boolean> = { sort: options.sort }
  if (options.fit === 'unscored') query.evaluated = false
  else if (options.fit !== 'any') query.fit_min = Number(options.fit)
  if (options.seen !== 'any') {
    query.from = new Date(now.getTime() - SEEN_MS[options.seen]).toISOString()
  }
  return query
}

/** True when a filter (not the sort order) narrows the list. */
export function hasActiveFilters(options: ListOptions): boolean {
  return options.fit !== 'any' || options.seen !== 'any'
}

const SORTS = Object.keys(SORT_LABELS) as SortKey[]

/** A stored sort key, or the default when it is missing or no longer valid. */
export function parseSort(value: string | null): SortKey {
  return SORTS.find((key) => key === value) ?? DEFAULT_OPTIONS.sort
}
