import { describe, expect, it } from 'vitest'
import { makeProfile } from '@/test/builders'
import { blankProfileForm, formFromProfile, profileProblem } from './form'

describe('formFromProfile', () => {
  it('turns the current revision into an editable form without provenance', () => {
    const form = formFromProfile(makeProfile())
    expect(form.headline).toBe('AI solutions engineer')
    expect(form.skills).toEqual([
      { name: 'Python', kind: 'technology', level: 'expert', years: 10 },
      { name: 'Kubernetes', kind: 'technology', level: 'advanced', years: 4 },
    ])
    expect(form.experience[0]).toEqual({
      title: 'Solutions Architect',
      organisation: 'Example Corp',
      start: '2019-01',
      end: '2024-06',
      summary: 'Led integrations.',
      sectors: [],
    })
    expect(form.education).toEqual([{ level: 'msc', field: 'Computer Science' }])
    expect(form.certifications).toEqual([{ name: 'Example Certification', year: 2022 }])
    expect(form.privacy).toEqual({
      schema_version: 1,
      redact_contact_details: true,
      allow_cloud_processing: false,
    })
  })

  it('starts a blank profile from an empty, invalid form', () => {
    const form = formFromProfile(makeProfile({}, 0))
    expect(form).toEqual(blankProfileForm())
    expect(profileProblem(form)).toMatch(/headline/i)
  })
})

describe('profileProblem', () => {
  const valid = () => formFromProfile(makeProfile())

  it('accepts a complete profile', () => {
    expect(profileProblem(valid())).toBeNull()
  })

  it('needs a headline and a base place', () => {
    expect(profileProblem({ ...valid(), headline: '  ' })).toMatch(/headline/i)
    const noPlace = valid()
    noPlace.base_location = { place: '', country: '', timezone: '' }
    expect(profileProblem(noPlace)).toMatch(/base place/i)
  })

  it('keeps years of experience between 0 and 70', () => {
    expect(profileProblem({ ...valid(), years_experience: -1 })).toMatch(/years/i)
    expect(profileProblem({ ...valid(), years_experience: 71 })).toMatch(/years/i)
  })

  it('rejects empty and duplicate skills', () => {
    const empty = valid()
    empty.skills.push({ name: ' ', kind: 'technology', level: 'beginner', years: 1 })
    expect(profileProblem(empty)).toMatch(/skill/i)
    const duplicate = valid()
    duplicate.skills.push({ name: 'python', kind: 'technology', level: 'beginner', years: 1 })
    expect(profileProblem(duplicate)).toMatch(/duplicate|twice/i)
  })

  it('keeps skill years within 0 to 70', () => {
    const form = valid()
    form.skills[0].years = 80
    expect(profileProblem(form)).toMatch(/skill/i)
  })

  it('needs a title, organisation and a start for each role, with the end not before the start', () => {
    const noTitle = valid()
    noTitle.experience[0].title = ''
    expect(profileProblem(noTitle)).toMatch(/role/i)
    const backwards = valid()
    backwards.experience[0].start = '2024-06'
    backwards.experience[0].end = '2019-01'
    expect(profileProblem(backwards)).toMatch(/end/i)
    const noStart = valid()
    noStart.experience[0].start = ''
    expect(profileProblem(noStart)).toMatch(/start/i)
  })

  it('needs valid two-letter language codes', () => {
    const form = valid()
    form.languages.push({ language: 'x', level: 'B1' })
    expect(profileProblem(form)).toMatch(/language/i)
  })
})

describe('career directions (ADR-057)', () => {
  const valid = () => formFromProfile(makeProfile())
  const direction = (label: string, text = 'I look for telecom billing roles.') => ({
    label,
    text,
    enabled: true,
  })

  it('a profile without directions gives an empty list', () => {
    expect(valid().directions).toEqual([])
    expect(blankProfileForm().directions).toEqual([])
  })

  it('carries the saved directions into the form, enabled or not', () => {
    const profile = makeProfile()
    profile.current_revision!.facts.directions = [
      direction('Billing SME'),
      { ...direction('AI engineer', 'Moving into AI.'), enabled: false },
    ]
    expect(formFromProfile(profile).directions).toEqual([
      direction('Billing SME'),
      { ...direction('AI engineer', 'Moving into AI.'), enabled: false },
    ])
  })

  it('accepts up to five directions with distinct labels', () => {
    const form = valid()
    form.directions = ['A', 'B', 'C', 'D', 'E'].map((label) => direction(label))
    expect(profileProblem(form)).toBeNull()
    form.directions.push(direction('F'))
    expect(profileProblem(form)).toMatch(/at most 5/i)
  })

  it('needs a label and a text for every direction', () => {
    const noLabel = valid()
    noLabel.directions = [direction(' ')]
    expect(profileProblem(noLabel)).toMatch(/label/i)
    const noText = valid()
    noText.directions = [direction('Billing SME', '  ')]
    expect(profileProblem(noText)).toMatch(/text/i)
  })

  it('refuses a text longer than 1,000 characters and repeated labels', () => {
    const long = valid()
    long.directions = [direction('Billing SME', 'x'.repeat(1001))]
    expect(profileProblem(long)).toMatch(/1,000/)
    const twice = valid()
    twice.directions = [direction('Billing SME'), direction('  billing  sme ', 'Another text.')]
    expect(profileProblem(twice)).toMatch(/twice/i)
  })
})
