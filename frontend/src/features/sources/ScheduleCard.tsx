import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { useSaveSchedule, useSchedule, type ScheduleRead } from './queries'

const ZONES: string[] =
  typeof Intl.supportedValuesOf === 'function' ? Intl.supportedValuesOf('timeZone') : []

function Form({ schedule }: { schedule: ScheduleRead }) {
  const save = useSaveSchedule()
  const [time, setTime] = useState(schedule.run_time_local)
  const [zone, setZone] = useState(schedule.timezone)
  const [enabled, setEnabled] = useState(schedule.enabled)
  const dirty =
    time !== schedule.run_time_local || zone !== schedule.timezone || enabled !== schedule.enabled
  const shown = save.data ?? schedule

  return (
    <form
      className="mt-3 flex flex-col gap-3 text-sm"
      onSubmit={(event) => {
        event.preventDefault()
        save.mutate({
          run_time_local: time,
          timezone: zone,
          enabled,
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
      <div className="grid grid-cols-2 gap-3">
        <label className="flex flex-col gap-1">
          Run time
          <input
            type="time"
            value={time}
            onChange={(event) => setTime(event.target.value)}
            className="rounded-md border border-line bg-surface px-2 py-1.5"
          />
        </label>
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
      </div>
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
        <Button type="submit" size="sm" disabled={!dirty || save.isPending}>
          Save schedule
        </Button>
      </div>
    </form>
  )
}

/**
 * Daily schedule: run time, IANA time zone and an on/off switch. The worker creates the run; this
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
