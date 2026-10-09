import { ChevronDown, ChevronRight, RefreshCw } from 'lucide-react'
import { Fragment, useState } from 'react'
import { Button } from '@/components/ui/button'
import { formatDateTime } from '@/lib/format'
import { BoardSettings } from './BoardSettings'
import type { CollectionRunRead, SourceRead, useJobBoardActions } from './queries'
import { StatusCell } from './StatusCell'

const COLUMNS = 7

interface Props {
  sources: SourceRead[]
  activeRun: CollectionRunRead | undefined
  busy: boolean
  actions: ReturnType<typeof useJobBoardActions>
  onRun: (source: SourceRead) => void
  onToggle: (source: SourceRead) => void
}

/** Whether the board asked not to be contacted again yet (its own minimum interval). */
function tooSoon(source: SourceRead): boolean {
  return (
    source.next_run_allowed_at !== null &&
    new Date(source.next_run_allowed_at).getTime() > Date.now()
  )
}

/**
 * Job boards with status in words and icons, counts, row actions and a settings panel per board
 * (second disclosure level). A board shows its coverage instead of a company, because it carries
 * the postings of many companies.
 */
export function JobBoardsTable({ sources, activeRun, busy, actions, onRun, onToggle }: Props) {
  const [open, setOpen] = useState<ReadonlySet<number>>(new Set())
  function toggleOpen(id: number) {
    setOpen((current) => {
      const next = new Set(current)
      if (!next.delete(id)) next.add(id)
      return next
    })
  }

  return (
    <table className="w-full border-collapse text-sm">
      <caption className="sr-only">Job boards and the result of their last run</caption>
      <thead>
        <tr className="border-b border-line text-left text-[11px] uppercase tracking-wider text-ink-3">
          <th scope="col" className="px-3.5 py-2 font-semibold">
            Board
          </th>
          <th scope="col" className="px-3.5 py-2 font-semibold">
            Status
          </th>
          <th scope="col" className="px-3.5 py-2 text-right font-semibold">
            Kept
          </th>
          <th scope="col" className="px-3.5 py-2 text-right font-semibold">
            New
          </th>
          <th scope="col" className="px-3.5 py-2 text-right font-semibold">
            Changed
          </th>
          <th scope="col" className="px-3.5 py-2 font-semibold">
            Last update
          </th>
          <th scope="col" className="px-3.5 py-2">
            <span className="sr-only">Actions</span>
          </th>
        </tr>
      </thead>
      <tbody>
        {sources.map((source) => {
          const id = source.source_configuration_id
          const result = source.last_result
          const expanded = open.has(id)
          const wait = tooSoon(source)
          return (
            <Fragment key={id}>
              <tr className="border-b border-line last:border-0">
                <td className="px-3.5 py-2.5">
                  <div className="font-medium">{source.display_name}</div>
                  <div className="text-xs text-ink-3">{source.coverage_note}</div>
                </td>
                <td className="px-3.5 py-2.5">
                  <StatusCell source={source} activeRun={activeRun} />
                  {wait && source.next_run_allowed_at && (
                    <div className="mt-0.5 text-xs text-ink-3">
                      Next run allowed {formatDateTime(source.next_run_allowed_at)}
                    </div>
                  )}
                </td>
                <td className="px-3.5 py-2.5 text-right">{source.open_postings}</td>
                <td className="px-3.5 py-2.5 text-right">{result ? result.new_count : '—'}</td>
                <td className="px-3.5 py-2.5 text-right">{result ? result.updated_count : '—'}</td>
                <td className="px-3.5 py-2.5 text-ink-2">
                  {result ? (
                    <time dateTime={result.finished_at}>{formatDateTime(result.finished_at)}</time>
                  ) : (
                    '—'
                  )}
                </td>
                <td className="whitespace-nowrap px-3.5 py-2.5 text-right">
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={busy || wait}
                    onClick={() => onRun(source)}
                    aria-label={`Run ${source.display_name} now`}
                  >
                    <RefreshCw /> Run now
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onToggle(source)}
                    aria-label={`${source.enabled ? 'Disable' : 'Enable'} ${source.display_name}`}
                  >
                    {source.enabled ? 'Disable' : 'Enable'}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-expanded={expanded}
                    aria-controls={`board-settings-${id}`}
                    aria-label={`Settings for ${source.display_name}`}
                    onClick={() => toggleOpen(id)}
                  >
                    Settings {expanded ? <ChevronDown /> : <ChevronRight />}
                  </Button>
                </td>
              </tr>
              {expanded && (
                <tr id={`board-settings-${id}`}>
                  <td colSpan={COLUMNS} className="p-0">
                    <BoardSettings source={source} actions={actions} />
                  </td>
                </tr>
              )}
            </Fragment>
          )
        })}
      </tbody>
    </table>
  )
}
