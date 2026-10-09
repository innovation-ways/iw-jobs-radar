import { RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { formatDateTime } from '@/lib/format'
import type { CollectionRunRead, SourceRead } from './queries'
import { StatusCell } from './StatusCell'

interface Props {
  sources: SourceRead[]
  activeRun: CollectionRunRead | undefined
  busy: boolean
  onRun: (source: SourceRead) => void
  onToggle: (source: SourceRead) => void
}

/** Configured boards with status in words and icons (never colour alone), counts and row actions. */
export function SourcesTable({ sources, activeRun, busy, onRun, onToggle }: Props) {
  return (
    <table className="w-full border-collapse text-sm">
      <caption className="sr-only">Configured boards and the result of their last run</caption>
      <thead>
        <tr className="border-b border-line text-left text-[11px] uppercase tracking-wider text-ink-3">
          <th scope="col" className="px-3.5 py-2 font-semibold">
            Company
          </th>
          <th scope="col" className="px-3.5 py-2 font-semibold">
            Status
          </th>
          <th scope="col" className="px-3.5 py-2 text-right font-semibold">
            Postings
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
          const result = source.last_result
          const name = source.company_name ?? source.display_name
          return (
            <tr key={source.source_configuration_id} className="border-b border-line last:border-0">
              <td className="px-3.5 py-2.5">
                <div className="font-medium">{name}</div>
                <div className="text-xs text-ink-3">{source.external_identifier}</div>
              </td>
              <td className="px-3.5 py-2.5">
                <StatusCell source={source} activeRun={activeRun} />
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
                  disabled={busy}
                  onClick={() => onRun(source)}
                  aria-label={`Run ${name} now`}
                >
                  <RefreshCw /> Run now
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => onToggle(source)}
                  aria-label={`${source.enabled ? 'Disable' : 'Enable'} ${name}`}
                >
                  {source.enabled ? 'Disable' : 'Enable'}
                </Button>
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
