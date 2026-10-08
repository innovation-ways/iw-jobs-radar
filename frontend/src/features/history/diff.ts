import { deepEqual } from '@/lib/deepEqual'

export interface Difference {
  /** Where in the content, for example `weights › compensation`. */
  path: string
  kind: 'changed' | 'added' | 'removed'
  before: string | null
  after: string | null
}

type Json = unknown

const NOT_SET = 'not set'

function isObject(value: Json): value is Record<string, Json> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** Remove provenance recursively: when a fact was accepted is not a change of the fact. */
function strip(value: Json): Json {
  if (Array.isArray(value)) return value.map(strip)
  if (isObject(value)) {
    return Object.fromEntries(
      Object.entries(value)
        .filter(([key]) => key !== 'provenance')
        .map(([key, item]) => [key, strip(item)]),
    )
  }
  return value
}

/** A short human label for a list item: its name, title or key, else compact JSON. */
function label(item: Json): string {
  if (isObject(item)) {
    const name = item.name ?? item.title ?? item.key ?? item.language
    if (typeof name === 'string') {
      const detail = typeof item.stance === 'string' ? `: ${item.stance}` : ''
      return `${name}${detail}`
    }
  }
  return typeof item === 'string' ? item : JSON.stringify(item)
}

function text(value: Json): string {
  if (value === null || value === undefined) return NOT_SET
  return typeof value === 'string'
    ? value
    : typeof value === 'object'
      ? JSON.stringify(value)
      : String(value)
}

function walk(before: Json, after: Json, path: string[], out: Difference[]): void {
  if (deepEqual(before, after)) return
  const where = path.join(' › ')
  if (isObject(before) && isObject(after)) {
    for (const key of [
      ...Object.keys(before),
      ...Object.keys(after).filter((k) => !(k in before)),
    ]) {
      walk(before[key], after[key], [...path, key], out)
    }
    return
  }
  if (Array.isArray(before) && Array.isArray(after)) {
    for (const item of before.filter((b) => !after.some((a) => deepEqual(a, b)))) {
      out.push({ path: where, kind: 'removed', before: label(item), after: null })
    }
    for (const item of after.filter((a) => !before.some((b) => deepEqual(a, b)))) {
      out.push({ path: where, kind: 'added', before: null, after: label(item) })
    }
    return
  }
  out.push({ path: where, kind: 'changed', before: text(before), after: text(after) })
}

/** What differs between two revisions' content, ignoring provenance. Empty when identical. */
export function diffRevisions(before: Json, after: Json): Difference[] {
  const out: Difference[] = []
  walk(strip(before), strip(after), [], out)
  return out
}
