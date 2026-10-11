import { cn } from '@/lib/utils'
import { formatAge } from '@/lib/format'
import { FitTile } from './FitTile'
import type { InboxItem } from './queries'
import { cardSignals } from './signals'

interface Props {
  item: InboxItem
  selected: boolean
  onSelect: () => void
}

const COMPANY_BOARDS = new Set(['greenhouse', 'lever', 'ashby'])

/** "via Himalayas" for a job-board posting, "also on Jobicy" when the company board has it too. */
function boardChip(item: InboxItem): string | null {
  const boards = item.sources.filter((source) => !COMPANY_BOARDS.has(source.source_type))
  if (boards.length === 0) return null
  const names = boards.map((source) => source.source_name).join(', ')
  return boards.length < item.sources.length ? `also on ${names}` : `via ${names}`
}

const SIGNAL_TONE: Record<string, string> = {
  match: 'text-good',
  mismatch: 'text-bad',
  unknown: 'text-ink-3',
}

/**
 * A job card: the fit tile on the left (the anchor, unlike a mail row), title, company and place,
 * and the signals that usually decide look-or-skip. Status is shown with an icon and words.
 */
export function JobRow({ item, selected, onSelect }: Props) {
  const isNew = item.state === 'unread' || item.state === 'updated_unread'
  const settled = item.state === 'ignored' || item.state === 'archived' || item.state === 'applied'
  return (
    <div
      role="option"
      aria-selected={selected}
      tabIndex={-1}
      onClick={onSelect}
      className={cn(
        'relative grid cursor-pointer grid-cols-[60px_minmax(0,1fr)_auto] items-start gap-3.5 rounded-[10px] border bg-surface px-3.5 py-3 group-data-[density=compact]/inbox:items-center group-data-[density=compact]/inbox:py-1.5',
        selected ? 'border-brand ring-1 ring-brand' : 'border-line hover:border-line-strong',
        (item.state === 'ignored' || item.state === 'archived') && 'opacity-60',
      )}
    >
      <FitTile item={item} />
      <div className="min-w-0">
        <div className="flex items-center gap-1.5 font-semibold">
          {item.is_shortlisted && (
            <span aria-label="Shortlisted" className="text-caution">
              ★
            </span>
          )}
          <span className="truncate">{item.title}</span>
          {isNew && (
            <span className="shrink-0 rounded bg-brand px-1.5 text-[11px] font-bold text-on-brand">
              {item.state === 'updated_unread' ? 'UPDATED' : 'NEW'}
            </span>
          )}
        </div>
        <div className="mt-px flex items-center gap-2 overflow-hidden text-[13px] whitespace-nowrap text-ink-2">
          <span>{item.company_name}</span>
          {item.locations.length > 0 && (
            <>
              <span className="text-ink-3">·</span>
              <span className="truncate">{item.locations.join('; ')}</span>
            </>
          )}
          {boardChip(item) && (
            <span className="shrink-0 rounded border border-line px-1.5 text-xs text-ink-3">
              {boardChip(item)}
            </span>
          )}
        </div>
        {item.evaluation?.recommendation === 'not_recommended' &&
          item.evaluation.gates.length > 0 && (
            // The first hard constraint explains why the job is out of the way (ADR-058).
            <p className="mt-1 truncate text-xs text-bad">
              Cannot apply: {item.evaluation.gates[0].reason}
            </p>
          )}
        <ul
          className="mt-2 flex flex-wrap gap-1.5 group-data-[density=compact]/inbox:hidden"
          aria-label="Signals"
        >
          {item.evaluated ? (
            cardSignals(item.signals).map((signal) => (
              <li
                key={signal.key}
                className={cn(
                  'inline-flex items-center gap-1.5 rounded-md border bg-surface px-2 py-px text-xs text-ink-2',
                  signal.status === 'mismatch' ? 'border-bad' : 'border-line',
                )}
              >
                <span
                  aria-hidden="true"
                  className={cn('text-[11px] font-bold', SIGNAL_TONE[signal.status])}
                >
                  {signal.symbol}
                </span>
                {signal.label}
                <span className="sr-only"> ({signal.word})</span>
              </li>
            ))
          ) : (
            <li className="inline-flex items-center rounded-md border border-line px-2 py-px text-xs text-ink-3">
              Awaiting evaluation
            </li>
          )}
        </ul>
      </div>
      <div className="flex flex-col items-end gap-1 text-xs whitespace-nowrap text-ink-3 tabular-nums">
        <span>{formatAge(item.first_seen_at)}</span>
        {item.sources.length > 1 && <span>{item.sources.length} sites</span>}
        {settled && (
          <span className="rounded-full border border-line-strong px-2 text-ink-2">
            {item.state}
          </span>
        )}
      </div>
    </div>
  )
}
