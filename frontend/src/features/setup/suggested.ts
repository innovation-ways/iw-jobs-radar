import type { IntentDefinition } from '@/features/profile/queries'
import type { components } from '@/api/schema'

export type IntentDefaults = components['schemas']['IntentDefaultsRead']

type Entry = { key: string; stance: 'preferred' | 'acceptable' | 'rejected' }

/** Set the suggested stances on the options of one group; options not suggested keep theirs. */
function withStances(entries: Entry[] | undefined, suggested: Record<string, string>): Entry[] {
  const next = (entries ?? []).map((entry) => ({
    ...entry,
    stance: (suggested[entry.key] as Entry['stance'] | undefined) ?? entry.stance,
  }))
  // A group where everything is rejected can never match: keep the first option acceptable.
  if (next.length > 0 && next.every((entry) => entry.stance === 'rejected')) {
    next[0] = { ...next[0], stance: 'acceptable' }
  }
  return next
}

/**
 * Start a new search intent from what the first pack the owner switched on suggests: stances for
 * work arrangement, working pattern and travel, the weights, and whether a missing licence rules a
 * job out. These are only suggestions: the owner sees every one of them in the intent form.
 */
export function applyPackDefaults(
  definition: IntentDefinition,
  defaults: IntentDefaults,
): IntentDefinition {
  if (defaults.pack_key === null) return definition
  return {
    ...definition,
    stances: {
      ...definition.stances,
      work_arrangements: withStances(
        definition.stances.work_arrangements,
        defaults.work_arrangements,
      ),
      schedules: withStances(definition.stances.schedules, defaults.schedules),
      travel_levels: withStances(definition.stances.travel_levels, defaults.travel_levels),
    },
    weights: { ...definition.weights, ...defaults.weights },
    filters: {
      ...definition.filters,
      reject_missing_credentials: defaults.reject_missing_credentials,
    },
  }
}
