import type { components } from '@/api/schema'
import type { JobBoardFilters } from './queries'

/** The filters a company board starts with when the owner opts in (the server's defaults). */
export const DEFAULT_FILTERS: JobBoardFilters = {
  schema_version: 1,
  categories: ['software', 'data', 'devops', 'security', 'telecom'],
  search_terms: [],
  max_age_days: 30,
  max_postings_per_run: 500,
}

/** Fill the optional fields of filters received from the API (it always sends all of them). */
export function withDefaults(
  filters: Partial<components['schemas']['JobBoardFilters']> | null | undefined,
): JobBoardFilters {
  filters = filters ?? {}
  return {
    schema_version: 1,
    categories: filters.categories ?? [],
    search_terms: filters.search_terms ?? [],
    max_age_days: filters.max_age_days ?? 30,
    max_postings_per_run: filters.max_postings_per_run ?? 500,
  }
}

/** The reason the filters cannot be used, or `null` when they are valid. */
export function filtersProblem(filters: JobBoardFilters): string | null {
  const age = filters.max_age_days
  const limit = filters.max_postings_per_run
  if (!Number.isInteger(age) || age < 1 || age > 365) return 'Posted within must be 1 to 365 days.'
  if (!Number.isInteger(limit) || limit < 1 || limit > 5000)
    return 'The per run limit must be 1 to 5,000 postings.'
  if (filters.categories.length === 0) return 'Choose at least one technology area.'
  return null
}
