import type { IntentDefinition, ProfileRead, TaxonomyRead } from '@/features/profile/queries'
import { DEFAULT_WEIGHTS } from './weights'

type StanceEntry = IntentDefinition['stances']['role_families'][number]

function entries(taxonomy: TaxonomyRead, kind: string): StanceEntry[] {
  const terms = taxonomy.groups.find((group) => group.kind === kind)?.terms ?? []
  return terms.map((term) => ({ key: term.term_key, stance: 'acceptable' }))
}

/**
 * A valid starting intent: every option of the closed groups acceptable, every role family
 * acceptable (that group may not be empty), no sector opinion, default weights. The base place,
 * time zone and languages come from the profile so the owner starts close to their situation.
 */
export function defaultIntentDefinition(
  taxonomy: TaxonomyRead,
  profile: ProfileRead,
): IntentDefinition {
  const facts = profile.current_revision?.facts
  const location = facts?.base_location
  return {
    schema_version: 1,
    title: 'My search',
    stances: {
      role_families: entries(taxonomy, 'role_family'),
      work_arrangements: entries(taxonomy, 'work_arrangement'),
      engagement_types: entries(taxonomy, 'engagement_type'),
      hours: { part_time: 'acceptable' },
      seniority_levels: entries(taxonomy, 'seniority_level'),
      sectors: [],
      employer_types: entries(taxonomy, 'employer_type'),
    },
    work_rules: {
      remote: { eligible_regions: ['EU'], timezone: location?.timezone ?? 'UTC' },
      onsite_hybrid: {
        base_place: location?.place ?? 'Not set',
        latitude: location?.latitude ?? 0,
        longitude: location?.longitude ?? 0,
        radius_km: 40,
      },
    },
    compensation: {
      employee_pay: null,
      contractor_day_rate: null,
      reject_below_minimum: true,
    },
    languages: {
      can_work_in: facts?.languages.length ? facts.languages.map((l) => l.language) : ['en'],
      reject_unspoken_required: true,
    },
    keywords: [],
    exclusions: { companies: [], words: [] },
    filters: {
      max_posting_age_days: null,
      needs_visa_or_relocation: false,
      reject_missing_credentials: false,
    },
    benefits_wanted: [],
    weights: { ...DEFAULT_WEIGHTS },
    alert_threshold: 65,
  }
}
