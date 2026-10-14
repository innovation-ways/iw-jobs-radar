import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { useSaveSchedule, useSchedule, type ScheduleRead } from '@/features/sources/queries'

/**
 * The fit below which recommended jobs are listed under "Set aside" instead of the inbox
 * (ADR-060, ADR-071). It is one owner-wide setting stored with the schedule, so it is saved on
 * its own and does not create an intent revision. 0 turns the rule off.
 */
export function SetAsideFloorCard() {
  const schedule = useSchedule()
  if (schedule.isPending || !schedule.data) {
    return (
      <p className="mt-4 text-sm text-ink-2" role="status">
        {schedule.isError ? 'The set-aside limit could not be loaded.' : 'Loading…'}
      </p>
    )
  }
  return <FloorForm key={schedule.data.version} schedule={schedule.data} />
}

function FloorForm({ schedule }: { schedule: ScheduleRead }) {
  const save = useSaveSchedule()
  const [floor, setFloor] = useState(schedule.set_aside_below_fit)
  const dirty = floor !== schedule.set_aside_below_fit

  return (
    <section
      aria-labelledby="set-aside-floor-title"
      className="mt-4 rounded-lg border border-line bg-surface p-4"
    >
      <h2 id="set-aside-floor-title" className="text-sm font-semibold">
        Set aside below
      </h2>
      <p className="mt-1 text-sm text-ink-2">
        Recommended jobs with a fit under this value go to &quot;Set aside&quot; and stay out of the
        inbox. Jobs that are not evaluated are never set aside, and 0 turns the rule off. It applies
        to every search intent and does not change any score.
      </p>
      <form
        className="mt-3 flex flex-wrap items-center gap-3 text-sm"
        onSubmit={(event) => {
          event.preventDefault()
          save.mutate({
            run_times_local: schedule.run_times_local,
            timezone: schedule.timezone,
            enabled: schedule.enabled,
            company_recency_days: schedule.company_recency_days,
            set_aside_below_fit: floor,
            expected_version: schedule.version,
          })
        }}
      >
        <input
          type="range"
          min={0}
          max={100}
          step={1}
          value={floor}
          aria-label="Set aside below fit"
          onChange={(event) => setFloor(Number(event.target.value))}
          className="w-64 max-w-full"
        />
        <output className="w-24 tabular-nums">{floor === 0 ? 'Off' : `Below ${floor}`}</output>
        <Button type="submit" size="sm" disabled={!dirty || save.isPending}>
          Save limit
        </Button>
      </form>
      {save.isError && (
        <p role="alert" className="mt-2 rounded-md bg-bad-bg px-3 py-2 text-sm text-bad">
          {save.error.message}
        </p>
      )}
    </section>
  )
}
