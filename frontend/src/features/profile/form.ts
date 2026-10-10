import type { components } from '@/api/schema'
import type { ProfileRead } from './queries'

type Schemas = components['schemas']

/** What the owner edits: the saved facts without provenance and with skills typed by name. */
export interface ProfileForm {
  headline: string
  base_location: Schemas['BaseLocation']
  years_experience: number
  languages: Schemas['LanguageSkill'][]
  skills: Schemas['SkillInput'][]
  experience: Schemas['ExperienceInput'][]
  education: Schemas['EducationInput'][]
  certifications: Schemas['CertificationInput'][]
  /** Goals in the owner's own words, judged against every new job (ADR-057). */
  directions: Schemas['CareerDirection'][]
  privacy: Schemas['ProfilePrivacy']
}

/** Limits of a career direction (the server enforces the same, ADR-057). */
export const MAX_DIRECTIONS = 5
export const MAX_DIRECTION_TEXT = 1000
export const MAX_DIRECTION_LABEL = 60

/** The empty form for a profile that has no revision yet (invalid until completed). */
export function blankProfileForm(): ProfileForm {
  return {
    headline: '',
    base_location: { place: '', country: '', timezone: '' },
    years_experience: 0,
    languages: [],
    skills: [],
    experience: [],
    education: [],
    certifications: [],
    directions: [],
    privacy: { schema_version: 1, redact_contact_details: true, allow_cloud_processing: false },
  }
}

/** Build the editable form from the profile's current revision. */
export function formFromProfile(profile: ProfileRead): ProfileForm {
  const revision = profile.current_revision
  if (!revision) return blankProfileForm()
  const facts = revision.facts
  return {
    headline: facts.headline,
    base_location: facts.base_location,
    years_experience: facts.years_experience,
    languages: facts.languages,
    // The kind of an existing skill is not returned and is not needed: known names resolve to it.
    skills: facts.skills.map((s) => ({
      name: s.name,
      kind: 'technology',
      level: s.level,
      years: s.years,
    })),
    experience: facts.experience.map((e) => ({
      title: e.title,
      organisation: e.organisation,
      start: e.start,
      end: e.end ?? null,
      summary: e.summary ?? '',
      sectors: e.sectors ?? [],
    })),
    education: facts.education.map((e) => ({ level: e.level, field: e.field })),
    certifications: facts.certifications.map((c) => ({ name: c.name, year: c.year ?? null })),
    directions: (facts.directions ?? []).map((d) => ({
      label: d.label,
      text: d.text,
      enabled: d.enabled,
    })),
    privacy: revision.privacy,
  }
}

const normalise = (name: string) =>
  name
    .toLowerCase()
    .replace(/[^a-z0-9+#]+/g, ' ')
    .trim()

/**
 * The first reason this draft cannot be saved, or `null`. It mirrors the server rules for instant
 * feedback; the server stays the authority and answers 422 for anything else.
 */
export function profileProblem(form: ProfileForm): string | null {
  if (!form.headline.trim()) return 'Add a headline.'
  const place = form.base_location
  if (!place.place || !/^[A-Z]{2}$/.test(place.country) || !place.timezone) {
    return 'Choose a base place from the suggestions.'
  }
  if (
    !Number.isInteger(form.years_experience) ||
    form.years_experience < 0 ||
    form.years_experience > 70
  ) {
    return 'Years of experience must be between 0 and 70.'
  }
  for (const language of form.languages) {
    if (!/^[a-z]{2}$/.test(language.language))
      return 'Each language needs a two-letter code, for example pt.'
  }
  const seen = new Set<string>()
  for (const skill of form.skills) {
    if (!skill.name.trim()) return 'Each skill needs a name.'
    if (skill.years < 0 || skill.years > 70)
      return `Skill "${skill.name}": years must be between 0 and 70.`
    const key = normalise(skill.name)
    if (seen.has(key)) return `The skill "${skill.name}" appears twice.`
    seen.add(key)
  }
  for (const role of form.experience) {
    if (!role.title.trim() || !role.organisation.trim())
      return 'Each role needs a title and an organisation.'
    if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(role.start))
      return `Role "${role.title}": add a start month.`
    if (role.end && role.end < role.start)
      return `Role "${role.title}": the end must not be before the start.`
  }
  if (form.directions.length > MAX_DIRECTIONS)
    return `Add at most ${MAX_DIRECTIONS} career directions.`
  const labels = new Set<string>()
  for (const direction of form.directions) {
    const label = direction.label.trim()
    if (!label) return 'Each career direction needs a label.'
    if (label.length > MAX_DIRECTION_LABEL)
      return `A direction label is at most ${MAX_DIRECTION_LABEL} characters.`
    if (!direction.text.trim())
      return `Direction "${label}": write the text of what you are looking for.`
    if (direction.text.trim().length > MAX_DIRECTION_TEXT)
      return `Direction "${label}": the text is at most 1,000 characters.`
    const key = normalise(label)
    if (labels.has(key)) return `The direction "${label}" appears twice.`
    labels.add(key)
  }
  return null
}
