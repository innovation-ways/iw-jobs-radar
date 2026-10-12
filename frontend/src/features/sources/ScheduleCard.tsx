import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { useSaveSchedule, useSchedule, type ScheduleRead } from './queries'

const ZONES: string[] =
  typeof Intl.supportedValuesOf === 'function' ? Intl.supportedValuesOf('timeZone') : []

const MAX_TIMES = 12

/** The next hour that is not taken yet, as the suggestion for a new run time. */
function suggestTime(taken: string[]): string {
  const latest = taken.filter(Boolean).sort().at(-1) ?? '08:00'
  for (let step = 1; step <= 24; step += 1) {
    const hour = (Number(latest.slice(0, 2)) + step) % 24
    const candidate = `${String(hour).padStart(2, '0')}:00`
    if (!taken.includes(candidate)) return candidate
  }
  return '12:00'
}

function Form({ schedule }: { schedule: ScheduleRead }) {
  const save = useSaveSchedule()
  const [times, setTimes] = useState<string[]>(schedule.run_times_local)
  const [zone, setZone] = useState(schedule.timezone)
  const [enabled, setEnabled] = useState(schedule.enabled)
  const [recency, setRecency] = useState(String(schedule.company_recency_days))
  const days = Number(recency)
  const validDays = Number.isInteger(days) && days >= 1 && days <= 365
  const [floorText, setFloorText] = useState(String(schedule.set_aside_below_fit))
  const floor = Number(floorText)
  const validFloor =
    floorText.trim() !== '' && Number.isInteger(floor) && floor >= 0 && floor <= 100
  const complete = times.every((value) => value !== '')
  const repeated = new Set(times).size !== times.length
  const validTimes = complete && !repeated
  // The server keeps the times sorted, so compare and send them that way.
  const sortedTimes = [...times].sort()
  const timesChanged = sortedTimes.join() !== schedule.run_times_local.join()
  const dirty =
    (validTimes && timesChanged) ||
    zone !== schedule.timezone ||
    enabled !== schedule.enabled ||
    (validDays && days !== schedule.company_recency_days) ||
    (validFloor && floor !== schedule.set_aside_below_fit)
  const shown = save.data ?? schedule

  return (
    <form
      className="mt-3 flex flex-col gap-3 text-sm"
      onSubmit={(event) => {
        event.preventDefault()
        save.mutate({
          run_times_local: validTimes ? sortedTimes : schedule.run_times_local,
          timezone: zone,
          enabled,
          company_recency_days: validDays ? days : schedule.company_recency_days,
          set_aside_below_fit: validFloor ? floor : schedule.set_aside_below_fit,
          expected_version: schedule.version,
        })
      }}
    >
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(event) => setEnabled(event.target.checked)}
        />
        Run every day
      </label>
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1">Run times (each day, in the time zone below)</legend>
        <ul className="flex flex-col gap-2">
          {times.map((value, index) => (
            <li key={index} className="flex items-center gap-2">
              <input
                type="time"
                aria-label={`Run time ${index + 1}`}
                value={value}
                onChange={(event) =>
                  setTimes(times.map((item, at) => (at === index ? event.target.value : item)))
                }
                className="rounded-md border border-line bg-surface px-2 py-1.5"
              />
              <Button
                type="button"
                variant="ghost"
                size="sm"
                aria-label={`Remove run time ${index + 1}`}
                disabled={times.length === 1}
                onClick={() => setTimes(times.filter((_, at) => at !== index))}
              >
                Remove
              </Button>
            </li>
          ))}
        </ul>
        <div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={times.length >= MAX_TIMES}
            onClick={() => setTimes([...times, suggestTime(times)])}
          >
            Add a run time
          </Button>
        </div>
        {!complete && <span className="text-bad">Fill in every run time.</span>}
        {complete && repeated && <span className="text-bad">Use each run time only once.</span>}
      </fieldset>
      <label className="flex flex-col gap-1">
        Time zone
        <input
          list="time-zones"
          value={zone}
          onChange={(event) => setZone(event.target.value)}
          className="rounded-md border border-line bg-surface px-2 py-1.5"
        />
        <datalist id="time-zones">
          {ZONES.map((name) => (
            <option key={name} value={name} />
          ))}
        </datalist>
      </label>
      <label className="flex flex-col gap-1">
        Company views: count offers first seen in the last (days)
        <input
          type="number"
          min={1}
          max={365}
          value={recency}
          onChange={(event) => setRecency(event.target.value)}
          aria-invalid={!validDays}
          className="w-28 rounded-md border border-line bg-surface px-2 py-1.5"
        />
        {!validDays && <span className="text-bad">Enter a whole number from 1 to 365.</span>}
      </label>
      <label className="flex flex-col gap-1">
        Inbox: set aside recommended jobs with a fit below (0 turns it off)
        <input
          type="number"
          min={0}
          max={100}
          value={floorText}
          onChange={(event) => setFloorText(event.target.value)}
          aria-invalid={!validFloor}
          className="w-28 rounded-md border border-line bg-surface px-2 py-1.5"
        />
        {!validFloor && <span className="text-bad">Enter a whole number from 0 to 100.</span>}
      </label>
      <p className="text-ink-2">
        {shown.enabled && shown.next_run_local
          ? `Next run: ${shown.next_run_local} (${shown.timezone})`
          : 'Scheduled runs are off. Use Run all now, or turn the schedule on.'}
      </p>
      {save.isError && (
        <p role="alert" className="rounded-md bg-bad-bg px-3 py-2 text-bad">
          {save.error.message}
        </p>
      )}
      <div>
        <Button
          type="submit"
          size="sm"
          disabled={!dirty || !validTimes || !validDays || !validFloor || save.isPending}
        >
          Save schedule
        </Button>
      </div>
    </form>
  )
}

/**
 * Daily schedule: one or more run times, IANA time zone and an on/off switch. The worker creates the run; this
 * card only edits the setting. The `key` re-initialises the form when the saved version changes.
 */
export function ScheduleCard() {
  const { data, isPending, isError } = useSchedule()
  return (
    <section aria-labelledby="schedule" className="rounded-lg border border-line bg-surface p-4">
      <h2 id="schedule" className="text-sm font-semibold">
        Daily schedule
      </h2>
      {isPending && <p className="mt-3 text-sm text-ink-3">Loading…</p>}
      {isError && (
        <p role="alert" className="mt-3 text-sm text-bad">
          Could not load the schedule.
        </p>
      )}
      {data && <Form key={data.version} schedule={data} />}
    </section>
  )
}
