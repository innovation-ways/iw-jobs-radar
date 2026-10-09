import {
  CircleAlert,
  CircleCheck,
  CircleDashed,
  CircleMinus,
  Loader,
  TriangleAlert,
} from 'lucide-react'
import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'
import type { CollectionRunRead, SourceRead } from './queries'
import { statusOf, type StatusKind } from './status'

const STATUS_STYLE: Record<StatusKind, { icon: ReactNode; tone: string }> = {
  running: { icon: <Loader className="size-3.5 animate-spin" />, tone: 'text-brand-text' },
  succeeded: { icon: <CircleCheck className="size-3.5" />, tone: 'text-good' },
  unchanged: { icon: <CircleCheck className="size-3.5" />, tone: 'text-good' },
  partial: { icon: <TriangleAlert className="size-3.5" />, tone: 'text-caution' },
  skipped: { icon: <CircleMinus className="size-3.5" />, tone: 'text-ink-3' },
  failed: { icon: <CircleAlert className="size-3.5" />, tone: 'text-bad' },
  never: { icon: <CircleDashed className="size-3.5" />, tone: 'text-ink-3' },
  disabled: { icon: <CircleMinus className="size-3.5" />, tone: 'text-ink-3' },
}

/**
 * The status of a source in words and an icon (never colour alone), plus the reason when the last
 * run failed. Shared by the company boards table and the job boards table.
 *
 * @param source the source whose last result is shown
 * @param activeRun the run in progress, if any, so a source being collected reads "Running"
 */
export function StatusCell({
  source,
  activeRun,
}: {
  source: SourceRead
  activeRun: CollectionRunRead | undefined
}) {
  const status = statusOf(source, activeRun)
  const style = STATUS_STYLE[status.kind]
  const result = source.last_result
  return (
    <>
      <span className={cn('inline-flex items-center gap-1.5 font-semibold', style.tone)}>
        {style.icon}
        {status.label}
      </span>
      {result?.outcome === 'failed' && (
        <div className="mt-0.5 text-xs text-bad">
          <span>{result.error_message ?? 'The run failed.'}</span>{' '}
          {result.error_class && <span className="font-mono">{result.error_class}</span>}
        </div>
      )}
    </>
  )
}
