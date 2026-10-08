import { cn } from '@/lib/utils'
import { bandOf, NOT_EVALUATED, TONE_CLASSES } from './bands'
import type { InboxItem } from './queries'

/** The score tile of a card: the fit number and its band in words, or "Pending" without a score. */
export function FitTile({ item }: { item: InboxItem }) {
  const evaluation = item.evaluation
  if (!evaluation) {
    return (
      <div className="w-[60px] rounded-lg border border-dashed border-line-strong py-1.5 text-center text-ink-3">
        <div className="text-xl leading-tight font-bold">—</div>
        <div className="text-[11px] font-semibold leading-tight">{NOT_EVALUATED.short}</div>
      </div>
    )
  }
  const band = bandOf(evaluation.fit_band)
  return (
    <div className={cn('w-[60px] rounded-lg py-1.5 text-center', TONE_CLASSES[band.tone].soft)}>
      <div className="text-[21px] leading-tight font-bold tabular-nums">{evaluation.fit_score}</div>
      <div className="text-[11px] font-semibold leading-tight">{band.short}</div>
    </div>
  )
}
