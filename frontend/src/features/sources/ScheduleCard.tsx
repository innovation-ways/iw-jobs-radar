/** Daily schedule: read-only until the background worker exists (implementation guide, T5). */
export function ScheduleCard() {
  return (
    <section aria-labelledby="schedule" className="rounded-lg border border-line bg-surface p-4">
      <h2 id="schedule" className="text-sm font-semibold">
        Daily schedule
      </h2>
      <p className="mt-3 text-sm text-ink-2">
        Scheduled daily runs are not available yet. They arrive with the background worker; until
        then, start a run with <strong>Run all now</strong> or from a board.
      </p>
    </section>
  )
}
