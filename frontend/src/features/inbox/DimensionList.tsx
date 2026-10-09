import { cn } from '@/lib/utils'
import { DIMENSIONS, OPTIONAL_DIMENSIONS } from '@/features/intent/weights'
import { signalIcon } from './signals'
import type { InboxDetail } from './queries'

type Dimension = InboxDetail['dimensions'][number]

const LABELS = new Map(
  [...DIMENSIONS, ...OPTIONAL_DIMENSIONS].map((d) => [d.key as string, d.label]),
)
const STATUS_TEXT = {
  match: 'Match',
  mismatch: 'Mismatch',
  unknown: 'Unknown — not stated',
} as const
const STATUS_BADGE = {
  match: 'bg-good-bg text-good',
  mismatch: 'bg-bad-bg text-bad',
  unknown: 'border border-dashed border-line-strong bg-band-bg text-band',
} as const

function quoteOf(dimension: Dimension): string | null {
  const quote = dimension.evidence.job_quote
  return typeof quote === 'string' && quote ? quote : null
}

/**
 * "Why this score": one row per dimension with its points. Hover or focus a row to see the
 * posting's own words and what it was compared with. Unstated facts are unknown and add nothing.
 */
export function DimensionList({ dimensions }: { dimensions: Dimension[] }) {
  const active = dimensions.filter((d) => !d.excluded)
  return (
    <ul className="flex flex-col">
      {active.map((dimension, index) => {
        const label = LABELS.get(dimension.dimension_key) ?? dimension.dimension_key
        const { symbol } = signalIcon(dimension)
        const quote = quoteOf(dimension)
        const opensUp = index >= active.length - 3
        return (
          <li
            key={dimension.dimension_key}
            tabIndex={0}
            aria-label={`${label}: ${dimension.status}, ${dimension.contribution} of ${dimension.weight} points. Show evidence`}
            className="group relative -mx-1.5 grid cursor-help grid-cols-[22px_1fr_auto] items-start gap-2.5 rounded-md border-t border-line px-1.5 py-2 first:border-t-0 hover:bg-surface-2 focus-visible:bg-surface-2"
          >
            <span
              aria-hidden="true"
              className={cn(
                'grid size-5 place-items-center rounded-full text-xs font-bold',
                STATUS_BADGE[dimension.status],
              )}
            >
              {symbol}
            </span>
            <div>
              <div className="font-semibold">
                {label}
                <span className="ml-1.5 text-xs font-medium text-ink-2">
                  <span>{STATUS_TEXT[dimension.status]}</span>
                  {dimension.status === 'match' && dimension.quality && (
                    <span> · {dimension.quality}</span>
                  )}
                </span>
              </div>
            </div>
            <div className="text-right font-semibold tabular-nums">
              {dimension.contribution}
              <small className="block text-[11px] font-normal text-ink-3">
                of {dimension.weight}
              </small>
            </div>
            <div
              role="tooltip"
              className={cn(
                'absolute right-0 left-[30px] z-10 hidden cursor-default rounded-[10px] border border-line-strong bg-surface p-3 text-left shadow-lg group-focus-within:block group-hover:block',
                opensUp ? 'bottom-[calc(100%-2px)]' : 'top-[calc(100%-2px)]',
              )}
            >
              <h4 className="mb-1 text-[11px] font-semibold tracking-wider text-ink-3 uppercase">
                What the posting says
              </h4>
              <blockquote className="mb-2.5 border-l-[3px] border-brand pl-2.5 text-[13px]">
                {quote ? `“${quote}”` : 'Not stated in the posting.'}
              </blockquote>
              <h4 className="mb-1 text-[11px] font-semibold tracking-wider text-ink-3 uppercase">
                Compared with your profile and intent
              </h4>
              <p className="text-[13px] text-ink-2">{dimension.explanation}</p>
              <p className="mt-2 text-[11px] text-ink-3">
                {dimension.contribution} of {dimension.weight} points
              </p>
            </div>
          </li>
        )
      })}
    </ul>
  )
}
