/** Human-readable labels and one-line summaries of proposed profile facts. */
export const PATH_LABELS: Record<string, string> = {
  headline: 'Headline',
  years_experience: 'Years of experience',
  base_location: 'Base location',
  languages: 'Language',
  skills: 'Skill',
  experience: 'Experience',
  education: 'Education',
  certifications: 'Certification',
}

type Value = string | number | Record<string, unknown> | null

/** A short text describing a proposed value, for the review list. */
export function summarise(path: string, value: unknown): string {
  const v = value as Value
  if (v === null || typeof v !== 'object') return String(v ?? '')
  const o = v as Record<string, unknown>
  switch (path) {
    case 'skills':
      return `${o.name} · ${o.level} · ${o.years} years`
    case 'languages':
      return `${o.language} · ${o.level}`
    case 'experience':
      return `${o.title} at ${o.organisation} (${o.start} – ${o.end ?? 'now'})`
    case 'education':
      return `${o.level} · ${o.field}`
    case 'certifications':
      return `${o.name}${o.year ? ` (${o.year})` : ''}`
    case 'base_location':
      return `${o.place}, ${o.country}`
    default:
      return JSON.stringify(v)
  }
}
