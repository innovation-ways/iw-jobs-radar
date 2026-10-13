import { Play } from 'lucide-react'
import { AddBoardCard } from '@/features/sources/AddBoardCard'
import { JobBoardsSection } from '@/features/sources/JobBoardsSection'
import { useJobBoardActions, useSourceActions, useSourcesData } from '@/features/sources/queries'
import { RunHistory } from '@/features/sources/RunHistory'
import { ScheduleCard } from '@/features/sources/ScheduleCard'
import { SourcesTable } from '@/features/sources/SourcesTable'
import { Button } from '@/components/ui/button'

/**
 * Sources screen: company boards (Greenhouse, one per company) and job boards (many companies,
 * added from a catalogue) with their last result, running one source or all enabled sources, and
 * the daily schedule.
 */
export function Sources() {
  const { sources, runs, activeRun } = useSourcesData()
  const companyBoards = sources.data?.filter((source) => source.category !== 'job_board')
  const jobBoards = sources.data?.filter((source) => source.category === 'job_board') ?? []
  const { addBoard, runSource, runAll, setEnabled } = useSourceActions()
  const boardActions = useJobBoardActions()
  const busy = Boolean(activeRun) || runSource.isPending || runAll.isPending
  const actionError = [runAll, runSource, setEnabled].find((mutation) => mutation.isError)?.error

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-4 px-4 sm:px-6 py-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <p className="text-ink-2">Company boards and job boards · one run per day by default</p>
        <Button onClick={() => runAll.mutate()} disabled={busy}>
          <Play /> Run all now
        </Button>
      </div>
      {activeRun && (
        <p role="status" className="rounded-md bg-brand-soft px-3.5 py-2 text-sm text-brand-text">
          A collection run is in progress. The list refreshes by itself.
        </p>
      )}
      {actionError && (
        <p role="alert" className="rounded-md bg-bad-bg px-3.5 py-2 text-sm text-bad">
          {actionError.message}
        </p>
      )}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <ScheduleCard />
        <AddBoardCard addBoard={addBoard} />
      </div>
      <section aria-labelledby="boards" className="rounded-lg border border-line bg-surface">
        <h2 id="boards" className="border-b border-line px-4 py-3 text-sm font-semibold">
          Company boards
        </h2>
        {sources.isPending && <p className="px-4 py-6 text-ink-3">Loading boards…</p>}
        {sources.isError && (
          <div role="alert" className="flex items-center gap-3 px-4 py-6 text-bad">
            Could not load the boards.
            <Button variant="outline" size="sm" onClick={() => void sources.refetch()}>
              Try again
            </Button>
          </div>
        )}
        {companyBoards?.length === 0 && (
          <p className="px-4 py-6 text-ink-2">
            No boards yet. Add a board token above to start collecting jobs.
          </p>
        )}
        {companyBoards && companyBoards.length > 0 && (
          <SourcesTable
            sources={companyBoards}
            actions={boardActions}
            activeRun={activeRun}
            busy={busy}
            onRun={(source) => runSource.mutate(source.source_configuration_id)}
            onToggle={(source) =>
              setEnabled.mutate({
                id: source.source_configuration_id,
                version: source.version,
                enabled: !source.enabled,
              })
            }
          />
        )}
      </section>
      <JobBoardsSection
        sources={jobBoards}
        activeRun={activeRun}
        busy={busy}
        onRun={(source) => runSource.mutate(source.source_configuration_id)}
      />
      {runs.data && <RunHistory runs={runs.data} />}
    </div>
  )
}
