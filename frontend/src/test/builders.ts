import type {
  IntentDefinition,
  IntentRead,
  ProfileRead,
  TaxonomyRead,
} from '@/features/profile/queries'
import { defaultIntentDefinition } from '@/features/intent/defaults'

/** A small synthetic taxonomy with the same shape as the real one. */
export const TAXONOMY: TaxonomyRead = {
  groups: [
    {
      kind: 'role_family',
      terms: [
        { term_key: 'ai_solutions_engineering', label: 'AI solutions engineering' },
        { term_key: 'data_analysis', label: 'Data analysis' },
      ],
    },
    {
      kind: 'work_arrangement',
      terms: [
        { term_key: 'remote', label: 'Remote' },
        { term_key: 'hybrid', label: 'Hybrid' },
        { term_key: 'onsite', label: 'On-site' },
      ],
    },
    {
      kind: 'engagement_type',
      terms: [
        { term_key: 'employee_permanent', label: 'Permanent employee' },
        { term_key: 'contractor_b2b', label: 'Contractor (B2B)' },
      ],
    },
    {
      kind: 'seniority_level',
      terms: [
        { term_key: 'junior', label: 'Junior' },
        { term_key: 'senior', label: 'Senior' },
      ],
    },
    {
      kind: 'sector',
      terms: [
        { term_key: 'telecom', label: 'Telecom' },
        { term_key: 'gambling', label: 'Gambling' },
      ],
    },
    {
      kind: 'employer_type',
      terms: [
        { term_key: 'direct_employer', label: 'Direct employer' },
        { term_key: 'agency', label: 'Agency or recruiter' },
      ],
    },
    { kind: 'benefit', terms: [{ term_key: 'equity', label: 'Equity' }] },
    {
      kind: 'schedule',
      terms: [
        { term_key: 'day', label: 'Day work' },
        { term_key: 'night', label: 'Night work' },
      ],
    },
    {
      kind: 'travel_level',
      terms: [
        { term_key: 'none', label: 'No travel' },
        { term_key: 'frequent', label: 'Frequent travel' },
      ],
    },
  ],
}

const provenance = {
  origin: 'manual' as const,
  evidence_id: null,
  accepted_at: '2026-10-08T10:00:00Z',
}

/** A profile with revision `revision` (or a blank one when `revision` is 0). */
export function makeProfile(overrides: Partial<ProfileRead> = {}, revision = 1): ProfileRead {
  return {
    career_profile_id: 1,
    title: 'AI Solutions',
    visibility: 'private',
    version: revision + 1,
    current_revision:
      revision === 0
        ? null
        : {
            profile_revision_id: 10 + revision,
            revision_number: revision,
            created_at: '2026-10-08T10:00:00Z',
            change_summary: null,
            privacy: {
              schema_version: 1,
              redact_contact_details: true,
              allow_cloud_processing: false,
            },
            facts: {
              schema_version: 1,
              headline: 'AI solutions engineer',
              base_location: {
                place: 'Lisbon, Portugal',
                country: 'PT',
                timezone: 'Europe/Lisbon',
                latitude: 38.72,
                longitude: -9.14,
              },
              years_experience: 12,
              languages: [{ language: 'pt', level: 'native' }],
              skills: [
                {
                  skill_id: 1,
                  name: 'Python',
                  kind: 'technology',
                  level: 'expert',
                  years: 10,
                  provenance,
                },
                {
                  skill_id: 2,
                  name: 'Kubernetes',
                  kind: 'technology',
                  level: 'advanced',
                  years: 4,
                  provenance,
                },
              ],
              experience: [
                {
                  title: 'Solutions Architect',
                  organisation: 'Example Corp',
                  start: '2019-01',
                  end: '2024-06',
                  summary: 'Led integrations.',
                  sectors: [],
                  provenance,
                },
              ],
              education: [{ level: 'msc', field: 'Computer Science', provenance }],
              certifications: [{ name: 'Example Certification', year: 2022, provenance }],
            },
          },
    ...overrides,
  }
}

/** An intent with revision `revision`, built from the synthetic taxonomy. */
export function makeIntent(
  overrides: Partial<IntentRead> = {},
  definition: IntentDefinition = defaultIntentDefinition(TAXONOMY, makeProfile()),
  revision = 1,
): IntentRead {
  return {
    search_intent_id: 5,
    career_profile_id: 1,
    title: definition.title,
    enabled: true,
    version: 1,
    current_revision: {
      intent_revision_id: 50 + revision,
      revision_number: revision,
      created_at: '2026-10-08T10:00:00Z',
      change_summary: null,
      definition,
    },
    ...overrides,
  }
}
