import { useState } from 'react'
import { useNavigate } from 'react-router'
import { Card } from '@/components/Card'
import { ChipsInput } from '@/components/ChipsInput'
import { LocationPicker } from '@/components/LocationPicker'
import { Button } from '@/components/ui/button'
import { describeApiError } from '@/api/errors'
import { defaultIntentDefinition } from '@/features/intent/defaults'
import { PackCard } from '@/features/packs/PackCard'
import { usePacks } from '@/features/packs/queries'
import { blankProfileForm, profileProblem, type ProfileForm } from '@/features/profile/form'
import { useProfileActions, useTaxonomy } from '@/features/profile/queries'
import { useIntentDefaults, skipSetup } from '@/features/setup/queries'
import { applyPackDefaults, type IntentDefaults } from '@/features/setup/suggested'

const field = 'rounded-md border border-line-strong bg-surface px-2.5 py-1.5 text-sm'
const STEPS = ['Fields of work', 'About you', 'Your first search'] as const

/** What the suggestions mean, in words, so the owner can see them before anything is created. */
function describeDefaults(defaults: IntentDefaults): string[] {
  const lines: string[] = []
  const arrangement = defaults.work_arrangements
  if (arrangement.onsite === 'preferred') lines.push('On-site work is preferred.')
  if (arrangement.remote === 'preferred') lines.push('Remote work is preferred.')
  if (arrangement.remote === 'rejected') lines.push('Remote work is ruled out.')
  if (defaults.schedules.day === 'preferred') lines.push('Day work is preferred.')
  if (defaults.reject_missing_credentials)
    lines.push('A job that needs a licence or certification you do not hold is ruled out.')
  if ((defaults.weights.qualifications ?? 0) > 0)
    lines.push('Licences and certifications count towards the score.')
  if ((defaults.weights.schedule_travel ?? 0) > 0)
    lines.push('Working pattern and travel count towards the score.')
  return lines
}

/**
 * First-run setup in three steps: choose the fields of work (packs), say who you are (headline,
 * place, experience, licences), then create the profile and a first search made from the packs'
 * suggestions. Everything stays editable in Profile & intent; the whole setup can be skipped.
 */
export function Setup() {
  const navigate = useNavigate()
  const packs = usePacks()
  const taxonomy = useTaxonomy()
  const defaults = useIntentDefaults()
  const { createProfile, saveProfile, createIntent } = useProfileActions()
  const [step, setStep] = useState(0)
  const [form, setForm] = useState<ProfileForm>(blankProfileForm())
  const [licences, setLicences] = useState<string[]>([])
  const [failure, setFailure] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const anyPack = (packs.data?.active_count ?? 0) > 0
  const profile = {
    ...form,
    skills: licences.map((name) => ({
      name,
      kind: 'credential' as const,
      level: 'expert' as const,
      years: 0,
    })),
  }
  const problem = profileProblem(profile)

  function leave() {
    skipSetup()
    navigate('/inbox')
  }

  async function create() {
    if (!taxonomy.data || !defaults.data) return
    setBusy(true)
    setFailure(null)
    try {
      const created = await createProfile.mutateAsync(form.headline.trim() || 'My profile')
      const saved = await saveProfile.mutateAsync({
        profileId: created.career_profile_id,
        body: {
          ...profile,
          expected_current_revision: null,
          change_summary: 'Created by the setup',
        },
      })
      await createIntent.mutateAsync({
        profileId: created.career_profile_id,
        definition: applyPackDefaults(
          defaultIntentDefinition(taxonomy.data, saved.profile),
          defaults.data,
        ),
      })
      navigate('/profile')
    } catch (error) {
      setFailure(describeApiError(error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4 px-4 sm:px-6 py-6">
      <ol aria-label="Steps" className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
        {STEPS.map((name, index) => (
          <li
            key={name}
            aria-current={index === step ? 'step' : undefined}
            className={index === step ? 'font-semibold text-ink' : 'text-ink-3'}
          >
            {index + 1}. {name}
          </li>
        ))}
      </ol>

      {step === 0 && (
        <>
          <h2 className="text-base font-semibold">Choose your fields of work</h2>
          <p className="text-sm text-ink-2">
            A pack is a ready-made list of role families, sectors, licences and areas of work for
            one field. Switch on the ones you search in; you can change this later in Packs.
          </p>
          {packs.isPending && <p className="text-sm text-ink-3">Loading…</p>}
          {packs.isError && (
            <p role="alert" className="text-sm text-bad">
              Could not load the packs.
            </p>
          )}
          {packs.data?.packs.map((pack) => (
            <PackCard key={pack.key} pack={pack} />
          ))}
          <div className="flex flex-wrap gap-2">
            <Button disabled={!anyPack} onClick={() => setStep(1)}>
              Continue
            </Button>
            <Button variant="outline" onClick={() => setStep(1)}>
              Start from scratch
            </Button>
          </div>
        </>
      )}

      {step === 1 && (
        <>
          <h2 className="text-base font-semibold">About you</h2>
          <Card
            title="Your profile"
            hint="Only what jobs are compared with. You can add more later."
          >
            <div className="flex flex-col gap-3">
              <label className="flex flex-col gap-1 text-xs text-ink-2">
                Headline
                <input
                  className={field}
                  value={form.headline}
                  maxLength={200}
                  placeholder="For example Maintenance electrician"
                  onChange={(event) => setForm({ ...form, headline: event.target.value })}
                />
              </label>
              <LocationPicker
                label="Base place"
                value={form.base_location.place}
                onSelect={(place) =>
                  setForm({
                    ...form,
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
              <label className="flex w-40 flex-col gap-1 text-xs text-ink-2">
                Years of experience
                <input
                  type="number"
                  min={0}
                  max={70}
                  className={field}
                  value={form.years_experience}
                  onChange={(event) =>
                    setForm({ ...form, years_experience: Number(event.target.value) })
                  }
                />
              </label>
              <ChipsInput
                label="Licences and certifications"
                values={licences}
                onChange={setLicences}
                placeholder="For example Driving licence (category B)"
              />
            </div>
          </Card>
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" onClick={() => setStep(0)}>
              Back
            </Button>
            <Button disabled={problem !== null} onClick={() => setStep(2)}>
              Continue
            </Button>
            {problem && <span className="text-xs text-ink-3">{problem}</span>}
            <Button variant="ghost" className="ml-auto" onClick={leave}>
              Skip the setup
            </Button>
          </div>
        </>
      )}

      {step === 2 && (
        <>
          <h2 className="text-base font-semibold">Your first search</h2>
          {defaults.isPending && <p className="text-sm text-ink-3">Loading…</p>}
          {defaults.data && (
            <Card
              title={
                defaults.data.pack_key
                  ? `Suggested by ${packs.data?.packs.find((p) => p.key === defaults.data.pack_key)?.name ?? 'your first pack'}`
                  : 'No pack suggestions'
              }
              hint="You will see and can change all of this in Profile & intent."
            >
              {describeDefaults(defaults.data).length > 0 ? (
                <ul className="list-disc pl-5 text-sm text-ink-2">
                  {describeDefaults(defaults.data).map((line) => (
                    <li key={line}>{line}</li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-ink-2">
                  The search starts with every option acceptable and the usual weights.
                </p>
              )}
            </Card>
          )}
          {failure && (
            <p role="alert" className="text-sm text-bad">
              {failure}
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" disabled={busy} onClick={() => setStep(1)}>
              Back
            </Button>
            <Button
              disabled={busy || !taxonomy.data || !defaults.data}
              onClick={() => void create()}
            >
              Create my profile and search
            </Button>
          </div>
        </>
      )}
    </div>
  )
}
