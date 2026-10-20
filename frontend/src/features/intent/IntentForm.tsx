import { Card } from '@/components/Card'
import { ChipsInput } from '@/components/ChipsInput'
import { LocationPicker } from '@/components/LocationPicker'
import type { IntentDefinition, TaxonomyRead } from '@/features/profile/queries'
import { ContractorFields, EmployeePayFields } from './PayFields'
import { replacementsOf } from './merge'
import { StanceGroup } from './StanceGroup'

interface Props {
  value: IntentDefinition
  onChange: (value: IntentDefinition) => void
  taxonomy: TaxonomyRead
}

const field = 'rounded-md border border-line-strong bg-surface px-2.5 py-1.5 text-sm'

const termsOf = (taxonomy: TaxonomyRead, kind: string) =>
  taxonomy.groups.find((group) => group.kind === kind)?.terms ?? []

const POSTING_AGE = [
  { value: '', label: 'Any time' },
  { value: '7', label: '7 days' },
  { value: '15', label: '15 days' },
  { value: '30', label: '30 days' },
]

/** Time zones the browser knows, for the remote time-zone field. */
function timeZones(current: string): string[] {
  const known =
    typeof Intl.supportedValuesOf === 'function' ? Intl.supportedValuesOf('timeZone') : []
  return known.includes(current) ? known : [current, ...known]
}

/**
 * The search-intent editor: what the owner is looking for (document 13, section 4). Every option
 * is Preferred, OK or Reject (Reject is a hard gate). All edits go to the parent draft; nothing
 * is saved until the owner presses Save revision.
 */
export function IntentForm({ value, onChange, taxonomy }: Props) {
  const set = (patch: Partial<IntentDefinition>) => onChange({ ...value, ...patch })
  const stances = (patch: Partial<IntentDefinition['stances']>) =>
    set({ stances: { ...value.stances, ...patch } })
  const { remote, onsite_hybrid: hybrid } = value.work_rules

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-ink-2">
        What you are looking for right now. For each option choose <strong>Preferred</strong>,{' '}
        <strong>OK</strong> or <strong>Reject</strong>. A rejected option rules a job out (Not
        recommended), whatever its score.
      </p>

      <Card title="Name">
        <label className="flex flex-col gap-1 text-xs text-ink-2">
          Intent name
          <input
            className={field}
            value={value.title}
            maxLength={120}
            onChange={(event) => set({ title: event.target.value })}
          />
        </label>
      </Card>

      <Card
        title="Roles"
        hint="Role families you want, accept or never want. Leave the others without opinion."
      >
        <StanceGroup
          label="Roles"
          terms={termsOf(taxonomy, 'role_family')}
          value={value.stances.role_families}
          onChange={(role_families) => stances({ role_families })}
          replacements={replacementsOf(taxonomy, 'role_family')}
          allowNoOpinion
        />
        <div className="mt-3">
          <ChipsInput
            label="Helpful keywords"
            values={value.keywords ?? []}
            onChange={(keywords) => set({ keywords })}
            placeholder="Add a keyword…"
          />
        </div>
      </Card>

      <Card
        title="Work arrangement & location"
        hint="Where you will work depends on the arrangement, so each one has its own place rule."
      >
        <StanceGroup
          label="Work arrangement"
          terms={termsOf(taxonomy, 'work_arrangement')}
          value={value.stances.work_arrangements}
          onChange={(work_arrangements) => stances({ work_arrangements })}
        />
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <div className="flex flex-col gap-2.5 rounded-md border border-line p-3">
            <p className="text-xs font-semibold text-ink-2">Remote: regions you can work from</p>
            <ChipsInput
              label="Remote regions"
              values={remote.eligible_regions}
              onChange={(eligible_regions) =>
                set({
                  work_rules: { ...value.work_rules, remote: { ...remote, eligible_regions } },
                })
              }
              normalise={(text) => text.toUpperCase()}
              validate={(text) =>
                /^([A-Z]{2}|EU|EEA|EUROPE|UK|WORLD)$/.test(text)
                  ? null
                  : 'Use a two-letter country code or EU, EEA, EUROPE, UK or WORLD.'
              }
              placeholder="EU, UK, PT…"
            />
            <label className="flex flex-col gap-1 text-xs text-ink-2">
              Remote time zone
              <select
                className={field}
                value={remote.timezone}
                onChange={(event) =>
                  set({
                    work_rules: {
                      ...value.work_rules,
                      remote: { ...remote, timezone: event.target.value },
                    },
                  })
                }
              >
                {timeZones(remote.timezone).map((zone) => (
                  <option key={zone}>{zone}</option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-xs text-ink-2">
              Time zone tolerance
              <select
                className={field}
                value={remote.timezone_tolerance_hours ?? ''}
                onChange={(event) =>
                  set({
                    work_rules: {
                      ...value.work_rules,
                      remote: {
                        ...remote,
                        timezone_tolerance_hours:
                          event.target.value === '' ? null : Number(event.target.value),
                      },
                    },
                  })
                }
              >
                <option value="">Any</option>
                <option value="2">±2 h</option>
                <option value="4">±4 h</option>
                <option value="6">±6 h</option>
              </select>
            </label>
          </div>
          <div className="flex flex-col gap-2.5 rounded-md border border-line p-3">
            <p className="text-xs font-semibold text-ink-2">Hybrid & on-site: stay within</p>
            <LocationPicker
              label="Base place"
              value={hybrid.base_place}
              onSelect={(place) =>
                set({
                  work_rules: {
                    remote: { ...remote, timezone: place.timezone },
                    onsite_hybrid: {
                      ...hybrid,
                      base_place: place.label,
                      latitude: place.latitude,
                      longitude: place.longitude,
                    },
                  },
                })
              }
            />
            <label className="flex flex-col gap-1 text-xs text-ink-2">
              Distance (km)
              <input
                inputMode="numeric"
                className={`${field} w-28`}
                value={hybrid.radius_km}
                onChange={(event) =>
                  set({
                    work_rules: {
                      ...value.work_rules,
                      onsite_hybrid: {
                        ...hybrid,
                        radius_km: Number(event.target.value.replace(/\D/g, '')) || 0,
                      },
                    },
                  })
                }
              />
            </label>
            <p className="text-xs text-ink-3">
              A remote job restricted to regions outside your list counts as Reject.
            </p>
          </div>
        </div>
      </Card>

      <Card title="Engagement">
        <StanceGroup
          label="Engagement"
          terms={termsOf(taxonomy, 'engagement_type')}
          value={value.stances.engagement_types}
          onChange={(engagement_types) => stances({ engagement_types })}
        />
        <div className="mt-3 flex items-center justify-between gap-2 border-t border-line pt-3">
          <span>Part-time</span>
          <StanceGroup
            label="Part-time"
            terms={[{ term_key: 'part_time', label: 'Part-time hours' }]}
            value={[{ key: 'part_time', stance: value.stances.hours.part_time }]}
            onChange={(entries) =>
              stances({ hours: { part_time: entries[0]?.stance ?? 'acceptable' } })
            }
          />
        </div>
      </Card>

      <Card
        title="Compensation"
        hint="Pay is compared in the form it is given: an annual salary for employees, a day rate for contractors, and only within one currency."
      >
        <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
          <div>
            <p className="mb-2 text-xs font-semibold text-ink-2">Employee · gross pay</p>
            <EmployeePayFields
              value={value.compensation.employee_pay ?? null}
              onChange={(employee_pay) =>
                set({ compensation: { ...value.compensation, employee_pay } })
              }
            />
          </div>
          <div>
            <p className="mb-2 text-xs font-semibold text-ink-2">
              Contractor / freelance · day rate
            </p>
            <ContractorFields
              value={value.compensation.contractor_day_rate ?? null}
              onChange={(contractor_day_rate) =>
                set({ compensation: { ...value.compensation, contractor_day_rate } })
              }
            />
          </div>
        </div>
        <label className="mt-3 flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={value.compensation.reject_below_minimum ?? true}
            onChange={(event) =>
              set({
                compensation: { ...value.compensation, reject_below_minimum: event.target.checked },
              })
            }
          />
          Reject jobs whose <em>stated</em> pay is below my minimum
        </label>
        <p className="mt-1 text-xs text-ink-3">
          If a posting does not state pay it counts as unknown and adds nothing to the score.
        </p>
      </Card>

      <Card title="Seniority">
        <StanceGroup
          label="Seniority"
          terms={termsOf(taxonomy, 'seniority_level')}
          value={value.stances.seniority_levels}
          onChange={(seniority_levels) => stances({ seniority_levels })}
        />
      </Card>

      <Card
        title="Domain & sector"
        hint="Sectors without opinion are neither preferred nor rejected."
      >
        <StanceGroup
          label="Sectors"
          terms={termsOf(taxonomy, 'sector')}
          value={value.stances.sectors ?? []}
          onChange={(sectors) => stances({ sectors })}
          replacements={replacementsOf(taxonomy, 'sector')}
          allowNoOpinion
        />
      </Card>

      <Card title="Employer">
        <StanceGroup
          label="Employer"
          terms={termsOf(taxonomy, 'employer_type')}
          value={value.stances.employer_types}
          onChange={(employer_types) => stances({ employer_types })}
        />
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <ChipsInput
            label="Companies to ignore"
            values={value.exclusions.companies ?? []}
            onChange={(companies) => set({ exclusions: { ...value.exclusions, companies } })}
            placeholder="Add a company…"
          />
          <ChipsInput
            label="Words in the posting that rule it out"
            values={value.exclusions.words ?? []}
            onChange={(words) => set({ exclusions: { ...value.exclusions, words } })}
            placeholder="Add a word…"
          />
        </div>
      </Card>

      <Card title="Languages">
        <ChipsInput
          label="I can work in (two-letter language codes, for example pt, en)"
          values={value.languages.can_work_in}
          onChange={(can_work_in) => set({ languages: { ...value.languages, can_work_in } })}
          normalise={(text) => text.toLowerCase()}
          validate={(text) => (/^[a-z]{2}$/.test(text) ? null : 'Use a two-letter language code.')}
        />
        <label className="mt-3 flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={value.languages.reject_unspoken_required ?? true}
            onChange={(event) =>
              set({
                languages: { ...value.languages, reject_unspoken_required: event.target.checked },
              })
            }
          />
          Reject postings that require a language I do not work in
        </label>
      </Card>

      <Card title="Other">
        <div className="flex flex-wrap items-end gap-4">
          <label className="flex flex-col gap-1 text-xs text-ink-2">
            Only jobs posted within
            <select
              className={field}
              value={value.filters.max_posting_age_days ?? ''}
              onChange={(event) =>
                set({
                  filters: {
                    ...value.filters,
                    max_posting_age_days:
                      event.target.value === '' ? null : Number(event.target.value),
                  },
                })
              }
            >
              {POSTING_AGE.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-2 pb-1.5 text-sm">
            <input
              type="checkbox"
              checked={value.filters.needs_visa_or_relocation ?? false}
              onChange={(event) =>
                set({
                  filters: { ...value.filters, needs_visa_or_relocation: event.target.checked },
                })
              }
            />
            I need visa sponsorship or relocation help
          </label>
          <label className="flex items-center gap-2 pb-1.5 text-sm">
            <input
              type="checkbox"
              checked={value.filters.reject_missing_credentials ?? false}
              onChange={(event) =>
                set({
                  filters: { ...value.filters, reject_missing_credentials: event.target.checked },
                })
              }
            />
            Rule out jobs that require a licence or certification I do not hold
          </label>
        </div>
        <div className="mt-4 flex items-center gap-3">
          <label htmlFor="alert-threshold" className="text-xs whitespace-nowrap text-ink-2">
            Alert threshold
          </label>
          <input
            id="alert-threshold"
            type="range"
            min={0}
            max={100}
            value={value.alert_threshold ?? 65}
            onChange={(event) => set({ alert_threshold: Number(event.target.value) })}
            className="flex-1 accent-[var(--accent)]"
          />
          <strong className="w-8 text-right tabular-nums">{value.alert_threshold ?? 65}</strong>
        </div>
        <p className="mt-1 text-xs text-ink-3">
          Jobs at or above this fit appear in the Today digest as high-fit.
        </p>
      </Card>
    </div>
  )
}
