import { Plus, Trash2 } from 'lucide-react'
import { useEffect } from 'react'
import { Card } from '@/components/Card'
import { DirtyBar } from '@/components/DirtyBar'
import { LocationPicker } from '@/components/LocationPicker'
import { Button } from '@/components/ui/button'
import { api } from '@/api/client'
import { unwrap } from '@/api/errors'
import { downloadJson } from '@/lib/download'
import { useDraft } from '@/lib/useDraft'
import { formFromProfile, profileProblem, type ProfileForm } from './form'
import { useProfileActions, type ProfileRead } from './queries'

const field = 'rounded-md border border-line-strong bg-surface px-2.5 py-1.5 text-sm'
const LEVELS = ['beginner', 'intermediate', 'advanced', 'expert'] as const
const LANGUAGE_LEVELS = ['A1', 'A2', 'B1', 'B2', 'C1', 'C2', 'native'] as const

interface Props {
  profile: ProfileRead
  onDirtyChange?: (dirty: boolean) => void
}

function replaceAt<T>(items: T[], index: number, patch: Partial<T>): T[] {
  return items.map((item, i) => (i === index ? { ...item, ...patch } : item))
}

const numberOf = (text: string) => Number(text.replace(/[^\d.]/g, '')) || 0

/**
 * Edits the career profile: summary, languages, skills and experience. Education and
 * certifications are kept as they are. Saving creates the next immutable revision.
 */
export function ProfilePanel({ profile, onDirtyChange }: Props) {
  const revision = profile.current_revision
  const { saveProfile } = useProfileActions()
  const { draft, setDraft, dirty, discard } = useDraft(
    formFromProfile(profile),
    revision?.profile_revision_id ?? `blank-${profile.career_profile_id}`,
  )
  useEffect(() => onDirtyChange?.(dirty), [dirty, onDirtyChange])
  const set = (patch: Partial<ProfileForm>) => setDraft({ ...draft, ...patch })

  async function exportProfile() {
    const data = await unwrap(
      api.GET('/api/v1/profiles/{career_profile_id}/export', {
        params: { path: { career_profile_id: profile.career_profile_id } },
      }),
    )
    downloadJson(`jobs-radar-profile-${profile.career_profile_id}.json`, data)
  }

  return (
    <>
      <div className="flex flex-col gap-4">
        <p className="text-sm text-ink-2">
          Your career facts, independent of any job search. Each change creates a new immutable
          revision; earlier revisions are kept.
          {revision ? (
            <span className="ml-2 text-ink-3">Current: revision {revision.revision_number}.</span>
          ) : (
            <span className="ml-2 text-ink-3">No revision yet: fill in the summary and save.</span>
          )}
        </p>

        <Card title="Summary">
          <div className="grid gap-3 md:grid-cols-2">
            <label className="flex flex-col gap-1 text-xs text-ink-2">
              Headline
              <input
                className={field}
                value={draft.headline}
                maxLength={200}
                onChange={(event) => set({ headline: event.target.value })}
              />
            </label>
            <LocationPicker
              label="Base place"
              value={draft.base_location.place}
              onSelect={(place) =>
                set({
                  base_location: {
                    place: place.label,
                    country: place.country,
                    timezone: place.timezone,
                    latitude: place.latitude,
                    longitude: place.longitude,
                  },
                })
              }
            />
            <label className="flex flex-col gap-1 text-xs text-ink-2">
              Years of experience
              <input
                inputMode="numeric"
                className={`${field} w-28`}
                value={draft.years_experience}
                onChange={(event) => set({ years_experience: numberOf(event.target.value) })}
              />
            </label>
          </div>
          <div className="mt-4">
            <div className="mb-1 flex items-center justify-between">
              <span className="text-xs text-ink-2">
                Languages (two-letter codes, for example pt, en)
              </span>
              <Button
                variant="outline"
                size="xs"
                onClick={() =>
                  set({ languages: [...draft.languages, { language: '', level: 'B2' }] })
                }
              >
                <Plus /> Add language
              </Button>
            </div>
            <ul className="flex flex-col gap-1.5">
              {draft.languages.map((language, index) => (
                <li key={index} className="flex items-center gap-2">
                  <input
                    aria-label="Language code"
                    maxLength={2}
                    className={`${field} w-16`}
                    value={language.language}
                    onChange={(event) =>
                      set({
                        languages: replaceAt(draft.languages, index, {
                          language: event.target.value.toLowerCase(),
                        }),
                      })
                    }
                  />
                  <select
                    aria-label="Language level"
                    className={field}
                    value={language.level}
                    onChange={(event) =>
                      set({
                        languages: replaceAt(draft.languages, index, {
                          level: event.target.value as (typeof LANGUAGE_LEVELS)[number],
                        }),
                      })
                    }
                  >
                    {LANGUAGE_LEVELS.map((level) => (
                      <option key={level}>{level}</option>
                    ))}
                  </select>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`Remove language ${language.language || index + 1}`}
                    onClick={() =>
                      set({ languages: draft.languages.filter((_, i) => i !== index) })
                    }
                  >
                    <Trash2 />
                  </Button>
                </li>
              ))}
            </ul>
          </div>
        </Card>

        <Card
          title="Skills"
          actions={
            <Button
              variant="outline"
              size="xs"
              onClick={() =>
                set({
                  skills: [
                    ...draft.skills,
                    { name: '', kind: 'technology', level: 'intermediate', years: 1 },
                  ],
                })
              }
            >
              <Plus /> Add skill
            </Button>
          }
        >
          {draft.skills.length === 0 ? (
            <p className="text-sm text-ink-3">No skills yet.</p>
          ) : (
            <table className="w-full text-sm">
              <caption className="sr-only">Skills with level and years</caption>
              <thead>
                <tr className="text-left text-[11px] tracking-wider text-ink-3 uppercase">
                  <th scope="col" className="py-1 font-semibold">
                    Skill
                  </th>
                  <th scope="col" className="py-1 font-semibold">
                    Level
                  </th>
                  <th scope="col" className="py-1 text-right font-semibold">
                    Years
                  </th>
                  <th scope="col" className="py-1">
                    <span className="sr-only">Remove</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {draft.skills.map((skill, index) => (
                  <tr key={index} className="border-t border-line">
                    <td className="py-1.5 pr-2">
                      <input
                        aria-label="Skill name"
                        className={`${field} w-full`}
                        value={skill.name}
                        onChange={(event) =>
                          set({
                            skills: replaceAt(draft.skills, index, { name: event.target.value }),
                          })
                        }
                      />
                    </td>
                    <td className="py-1.5 pr-2">
                      <select
                        aria-label="Skill level"
                        className={field}
                        value={skill.level}
                        onChange={(event) =>
                          set({
                            skills: replaceAt(draft.skills, index, {
                              level: event.target.value as (typeof LEVELS)[number],
                            }),
                          })
                        }
                      >
                        {LEVELS.map((level) => (
                          <option key={level}>{level}</option>
                        ))}
                      </select>
                    </td>
                    <td className="py-1.5 pr-2 text-right">
                      <input
                        aria-label="Skill years"
                        inputMode="decimal"
                        className={`${field} w-20 text-right`}
                        value={skill.years}
                        onChange={(event) =>
                          set({
                            skills: replaceAt(draft.skills, index, {
                              years: numberOf(event.target.value),
                            }),
                          })
                        }
                      />
                    </td>
                    <td className="py-1.5 text-right">
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label={`Remove ${skill.name || 'skill'}`}
                        onClick={() => set({ skills: draft.skills.filter((_, i) => i !== index) })}
                      >
                        <Trash2 />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>

        <Card
          title="Experience"
          actions={
            <Button
              variant="outline"
              size="xs"
              onClick={() =>
                set({
                  experience: [
                    ...draft.experience,
                    { title: '', organisation: '', start: '', end: null, summary: '', sectors: [] },
                  ],
                })
              }
            >
              <Plus /> Add role
            </Button>
          }
        >
          {draft.experience.length === 0 && <p className="text-sm text-ink-3">No roles yet.</p>}
          <ul className="flex flex-col gap-3">
            {draft.experience.map((role, index) => (
              <li key={index} className="rounded-md border border-line p-3">
                <div className="grid gap-2 md:grid-cols-2">
                  <label className="flex flex-col gap-1 text-xs text-ink-2">
                    Title
                    <input
                      aria-label="Role title"
                      className={field}
                      value={role.title}
                      onChange={(event) =>
                        set({
                          experience: replaceAt(draft.experience, index, {
                            title: event.target.value,
                          }),
                        })
                      }
                    />
                  </label>
                  <label className="flex flex-col gap-1 text-xs text-ink-2">
                    Organisation
                    <input
                      aria-label="Role organisation"
                      className={field}
                      value={role.organisation}
                      onChange={(event) =>
                        set({
                          experience: replaceAt(draft.experience, index, {
                            organisation: event.target.value,
                          }),
                        })
                      }
                    />
                  </label>
                  <label className="flex flex-col gap-1 text-xs text-ink-2">
                    Start
                    <input
                      type="month"
                      aria-label="Role start"
                      className={field}
                      value={role.start}
                      onChange={(event) =>
                        set({
                          experience: replaceAt(draft.experience, index, {
                            start: event.target.value,
                          }),
                        })
                      }
                    />
                  </label>
                  <label className="flex flex-col gap-1 text-xs text-ink-2">
                    End (empty if current)
                    <input
                      type="month"
                      aria-label="Role end"
                      className={field}
                      value={role.end ?? ''}
                      onChange={(event) =>
                        set({
                          experience: replaceAt(draft.experience, index, {
                            end: event.target.value || null,
                          }),
                        })
                      }
                    />
                  </label>
                </div>
                <label className="mt-2 flex flex-col gap-1 text-xs text-ink-2">
                  Summary
                  <textarea
                    aria-label="Role summary"
                    rows={2}
                    className={field}
                    value={role.summary ?? ''}
                    onChange={(event) =>
                      set({
                        experience: replaceAt(draft.experience, index, {
                          summary: event.target.value,
                        }),
                      })
                    }
                  />
                </label>
                <div className="mt-2 text-right">
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-label={`Remove role ${role.title || index + 1}`}
                    onClick={() =>
                      set({ experience: draft.experience.filter((_, i) => i !== index) })
                    }
                  >
                    <Trash2 /> Remove role
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        </Card>

        {(draft.education.length > 0 || draft.certifications.length > 0) && (
          <Card
            title="Education & certifications"
            hint="Kept as they are; editing arrives with the CV import review."
          >
            <ul className="list-disc pl-5 text-sm text-ink-2">
              {draft.education.map((item) => (
                <li key={`${item.level}-${item.field}`}>
                  {item.level} · {item.field}
                </li>
              ))}
              {draft.certifications.map((item) => (
                <li key={item.name}>
                  {item.name}
                  {item.year ? ` (${item.year})` : ''}
                </li>
              ))}
            </ul>
          </Card>
        )}

        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-line bg-surface px-4 py-3">
          <span className="flex-1 text-sm text-ink-2">Your data stays on this machine.</span>
          <Button variant="outline" onClick={() => void exportProfile()}>
            Export profile (JSON)
          </Button>
        </div>
      </div>
      <DirtyBar
        dirty={dirty}
        saving={saveProfile.isPending}
        problem={profileProblem(draft)}
        error={saveProfile.error?.message ?? null}
        onDiscard={() => {
          saveProfile.reset()
          discard()
        }}
        onSave={(summary) =>
          saveProfile.mutate({
            profileId: profile.career_profile_id,
            body: {
              ...draft,
              expected_current_revision: revision?.revision_number ?? null,
              change_summary: summary || null,
            },
          })
        }
      />
    </>
  )
}
