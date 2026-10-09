import { ChevronDown } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'
import { usePipelineStatus } from '@/features/pipeline/queries'
import {
  headline,
  pace,
  type PipelineQueue,
  type PipelineStatus as Status,
} from '@/features/pipeline/summary'
import { cn } from '@/lib/utils'

const TONE: Record<Status['state'], string> = {
  idle: 'bg-good',
  working: 'bg-brand',
  no_ai: 'bg-band',
  no_progress: 'bg-caution',
  worker_stopped: 'bg-bad',
}

/** A progress bar with its words; the number is never left to the bar alone. */
function Stage({
  label,
  done,
  queue,
  perMinute,
}: {
  label: string
  done: string
  queue: PipelineQueue
  perMinute: number
}) {
  const detail = [
    queue.waiting > 0 ? `${queue.waiting} waiting` : null,
    queue.failed > 0 ? `${queue.failed} failed` : null,
  ].filter(Boolean)
  return (
    <div>
      <div className="font-medium text-ink-2">{done}</div>
      <progress
        aria-label={label}
        className="mt-0.5 h-1.5 w-full"
        value={queue.done}
        max={Math.max(queue.total, 1)}
      />
      <div>
        {[...detail, pace(queue, perMinute)].filter(Boolean).join(' · ') || 'nothing waiting'}
      </div>
    </div>
  )
}

/**
 * Sidebar summary of the background work (analysis and scoring), expandable into the details:
 * progress per stage, pace, time left, the worker and the last failure. Polls faster while open.
 */
export function PipelineStatus() {
  const [open, setOpen] = useState(false)
  const { data } = usePipelineStatus(open)
  // No answer (first request, or the API is down): stay quiet, the API status line says why.
  if (!data) return null
  const line = pace(
    data.analysis.waiting > 0 ? data.analysis : data.scoring,
    data.analysis.waiting > 0 ? data.recent.analysed_per_minute : data.recent.scored_per_minute,
  )
  return (
    <div className="mt-2 text-xs text-ink-3">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="flex w-full items-start gap-2 text-left"
      >
        <span
          aria-hidden="true"
          className={cn('mt-1 size-2 shrink-0 rounded-full', TONE[data.state])}
        />
        <span className="flex-1">
          <span className="block font-medium text-ink-2">{headline(data)}</span>
          {line && <span className="block">{line}</span>}
        </span>
        <ChevronDown
          aria-hidden="true"
          className={cn('mt-0.5 size-3.5 shrink-0', open && 'rotate-180')}
        />
      </button>
      {open && (
        <div role="region" aria-label="Pipeline details" className="mt-2 flex flex-col gap-2.5">
          <Stage
            label="Analysis progress"
            done={`${data.analysis.done} of ${data.analysis.total} analysed`}
            queue={data.analysis}
            perMinute={data.recent.analysed_per_minute}
          />
          <Stage
            label="Scoring progress"
            done={`${data.scoring.done} of ${data.scoring.total} scored`}
            queue={data.scoring}
            perMinute={data.recent.scored_per_minute}
          />
          <p>Jobs are scored after they are analysed.</p>
          <div>
            Worker {data.worker.status}
            {data.ai_model ? ` · model ${data.ai_model}` : ' · no model'}
          </div>
          {data.failures.count > 0 && (
            <div>Last failure: {data.failures.last_error_class ?? 'unknown reason'}</div>
          )}
          <Link to="/inbox?fit=unscored" className="underline">
            Show jobs not evaluated
          </Link>
        </div>
      )}
    </div>
  )
}
