import type { components } from '@/api/schema'

type Schemas = components['schemas']
export type Item = Schemas['InboxItemSummary']
export type Detail = Schemas['InboxItemDetail']
export type Dimension = Schemas['DimensionRead']

let next = 1

/** A synthetic inbox card; override what a test cares about. */
export function makeItem(overrides: Partial<Item> = {}): Item {
  const id = overrides.job_inbox_item_id ?? next++
  return {
    job_inbox_item_id: id,
    job_opportunity_id: 100 + id,
    job_posting_id: 200 + id,
    state: 'unread',
    is_shortlisted: false,
    version: 1,
    title: `Senior AI Engineer ${id}`,
    company_id: 700 + id,
    company_name: 'Northwind Labs',
    locations: ['Remote - EU'],
    first_seen_at: '2026-10-08T10:00:00Z',
    last_seen_at: '2026-10-08T10:00:00Z',
    closed: false,
    evaluated: true,
    evaluation: {
      match_evaluation_id: 900 + id,
      policy_version: 'matching-v1.8',
      fit_score: 82,
      fit_band: 'excellent',
      recommendation: 'recommended',
      gates: [],
      profile_revision_id: 3,
      intent_revision_id: 2,
      created_at: '2026-10-08T10:05:00Z',
    },
    signals: [
      {
        dimension_key: 'work_arrangement_location',
        status: 'match',
        quality: 'strong',
        excluded: false,
      },
      { dimension_key: 'engagement_terms', status: 'match', quality: 'strong', excluded: false },
      { dimension_key: 'compensation', status: 'unknown', quality: null, excluded: false },
      { dimension_key: 'skills_technology', status: 'match', quality: 'partial', excluded: false },
    ],
    sources: [
      {
        job_posting_id: 200 + id,
        source_type: 'greenhouse',
        source_name: 'Northwind Careers',
        url: `https://jobs.example.test/${id}`,
        first_seen_at: '2026-10-08T10:00:00Z',
        closed: false,
        job_opportunity_link_id: 300 + id,
        link_state: 'auto',
        similarity: 1,
      },
    ],
    possible_duplicate: false,
    applied_at: null,
    note: null,
    engagement_types: [],
    pay: null,
    ...overrides,
  }
}

/** A card that has no score yet ("not evaluated"). */
export function makeUnscored(overrides: Partial<Item> = {}): Item {
  return makeItem({ evaluated: false, evaluation: null, signals: [], ...overrides })
}

export function makeDimension(overrides: Partial<Dimension> = {}): Dimension {
  return {
    dimension_key: 'work_arrangement_location',
    status: 'match',
    quality: 'strong',
    weight: 15,
    effective_weight: 15,
    strength: 1,
    contribution: 15,
    excluded: false,
    evidence: {
      job_quote: 'Fully remote within EU time zones.',
      compared: { remote: 'preferred' },
    },
    explanation: 'Remote work is open from your region.',
    ...overrides,
  }
}

export function makeDetail(item: Item, overrides: Partial<Detail> = {}): Detail {
  return {
    ...item,
    description_text:
      'Design and evaluate LLM-powered features.\nFully remote within EU time zones.',
    apply_url: 'https://careers.example.test/apply/1',
    source_url: 'https://careers.example.test/jobs/1',
    read_at: null,
    ignore_reason: null,
    application_url: null,
    dimensions: item.evaluated
      ? [
          makeDimension(),
          makeDimension({
            dimension_key: 'compensation',
            status: 'unknown',
            quality: null,
            weight: 10,
            effective_weight: 10,
            strength: 0,
            contribution: 0,
            evidence: { reason: 'The posting does not state pay.' },
            explanation: 'The posting does not state pay.',
          }),
        ]
      : [],
    events: [],
    last_change: null,
    brief: { summary: null, summary_model: null, technologies: [], facts: [] },
    ...overrides,
  }
}

export function makeCounts(
  overrides: Partial<Schemas['InboxCounts']> = {},
): Schemas['InboxCounts'] {
  return {
    unread: 4,
    set_aside: 6,
    read: 2,
    updated_unread: 1,
    ignored: 3,
    archived: 0,
    applied: 1,
    shortlisted: 2,
    total: 11,
    ...overrides,
  }
}
