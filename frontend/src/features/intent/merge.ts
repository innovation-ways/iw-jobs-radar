import type { IntentDefinition, TaxonomyRead } from '@/features/profile/queries'

type StanceEntry = IntentDefinition['stances']['role_families'][number]

/** The terms of one vocabulary that were merged into another: old key → key that replaced it. */
export function replacementsOf(taxonomy: TaxonomyRead, kind: string): Record<string, string> {
  return Object.fromEntries(
    (taxonomy.replacements ?? [])
      .filter((replacement) => replacement.kind === kind)
      .map((replacement) => [replacement.from_key, replacement.to_key]),
  )
}

/**
 * Express saved stances in the terms that exist after merges (ADR-080), as the server does when it
 * scores: a stance on a merged term becomes the stance of the term that replaced it, and when the
 * owner had also chosen one for that term, the surviving term's own choice wins.
 */
export function resolveStances(
  entries: StanceEntry[],
  replacements: Record<string, string>,
): StanceEntry[] {
  const kept = entries.filter((entry) => !(entry.key in replacements))
  const taken = new Set(kept.map((entry) => entry.key))
  const carried: StanceEntry[] = []
  for (const entry of entries) {
    const into = replacements[entry.key]
    if (into === undefined || taken.has(into)) continue
    taken.add(into)
    carried.push({ key: into, stance: entry.stance })
  }
  return [...kept, ...carried]
}
