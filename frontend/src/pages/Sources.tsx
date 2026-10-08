import { Play } from 'lucide-react'
import { AddBoardCard } from '@/features/sources/AddBoardCard'
import { useSourceActions, useSourcesData } from '@/features/sources/queries'
import { RunHistory } from '@/features/sources/RunHistory'
import { ScheduleCard } from '@/features/sources/ScheduleCard'
import { SourcesTable } from '@/features/sources/SourcesTable'
import { Button } from '@/components/ui/button'

/**
 * Sources screen: configured Greenhouse boards with their last result, adding a board, running one
 * board or all enabled boards, and the daily schedule.
 */
export function Sources() {
  const { sources, runs, activeRun } = useSourcesData()
  const { addBoard, runSource, runAll, setEnabled } = useSourceActions()
  const busy = Boolean(activeRun) || runSource.isPending || runAll.isPending
  const actionError = [runAll, runSource, setEnabled].find((mutation) => mutation.isError)?.error

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-4 px-6 py-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <p className="text-ink-2">Greenhouse job boards · one board per company</p>
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
      <div className="grid gap-4 md:grid-cols-2">
        <ScheduleCard />
        <AddBoardCard addBoard={addBoard} />
      </div>
      <section aria-labelledby="boards" className="rounded-lg border border-line bg-surface">
        <h2 id="boards" className="border-b border-line px-4 py-3 text-sm font-semibold">
          Configured boards
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
        {sources.data?.length === 0 && (
          <p className="px-4 py-6 text-ink-2">
            No boards yet. Add a board token above to start collecting jobs.
          </p>
        )}
        {sources.data && sources.data.length > 0 && (
          <SourcesTable
            sources={sources.data}
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
      {runs.data && <RunHistory runs={runs.data} />}
    </div>
  )
}
