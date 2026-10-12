import { ExternalLink } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { formatAge, formatDateTime } from '@/lib/format'
import { bandOf, NOT_EVALUATED, TONE_CLASSES } from './bands'
import { AssessDirections } from './AssessDirections'
import { DimensionList } from './DimensionList'
import { JobBrief } from './JobBrief'
import type { InboxDetail } from './queries'
import type { OwnerAction } from './undo'

interface Props {
  detail: InboxDetail
  busy: boolean
  onAction: (action: OwnerAction) => void
  onLinkDecision: (linkId: number, decision: 'confirm' | 'reject') => void
}

/**
 * A label whose first letter is the underlined hotkey. The whole word is one element: the buttons
 * are flex containers with a gap, so a separate letter would be spaced away from the rest.
 */
function Hotkey({ children }: { children: string }) {
  return (
    <span>
      <u className="underline-offset-2">{children[0]}</u>
      {children.slice(1)}
    </span>
  )
}

function ActionBar({ detail, busy, onAction }: Omit<Props, 'onLinkDecision'>) {
  const settled =
    detail.state === 'ignored' || detail.state === 'archived' || detail.state === 'applied'
  const star = (
    <Button
      variant="outline"
      disabled={busy}
      onClick={() => onAction(detail.is_shortlisted ? 'unshortlist' : 'shortlist')}
    >
      {detail.is_shortlisted ? (
        <>
          <span>
            ★ <u className="underline-offset-2">S</u>hortlisted — remove
          </span>
        </>
      ) : (
        <>
          <span>
            ☆ <u className="underline-offset-2">S</u>hortlist
          </span>
        </>
      )}
    </Button>
  )
  const original = detail.apply_url && (
    <Button asChild variant={settled ? 'outline' : 'default'}>
      {/* Opening the page does not change the job: only a button moves it out of "To review". */}
      <a href={detail.apply_url} target="_blank" rel="noopener noreferrer">
        <Hotkey>Open original</Hotkey>
        <ExternalLink />
      </a>
    </Button>
  )
  return (
    <div className="sticky bottom-0 z-[4] flex flex-wrap items-center gap-2 border-t border-line bg-surface px-5 py-2.5">
      {settled ? (
        <Button disabled={busy} onClick={() => onAction('restore')}>
          {detail.state === 'applied' ? '↩ Undo applied' : '↩ Restore'}{' '}
          <kbd className="text-[11px] opacity-70">r</kbd>
        </Button>
      ) : (
        original
      )}
      {settled && original}
      {star}
      {!settled && (
        <>
          {(detail.state === 'unread' || detail.state === 'updated_unread') && (
            <Button variant="outline" disabled={busy} onClick={() => onAction('open')}>
              <Hotkey>Mark as read</Hotkey>
            </Button>
          )}
          <Button variant="outline" disabled={busy} onClick={() => onAction('ignore')}>
            <Hotkey>Ignore</Hotkey>
          </Button>
          <Button variant="outline" disabled={busy} onClick={() => onAction('archive')}>
            <Hotkey>Archive</Hotkey>
          </Button>
          <Button variant="ghost" disabled={busy} onClick={() => onAction('record_application')}>
            Mark applied
          </Button>
        </>
      )}
    </div>
  )
}

/**
 * The detail panel: score with its band, the hard constraints that fired, why the score is what
 * it is (with evidence on hover or focus), where the job was seen, the description and actions.
 * The briefing (AI summary, technologies, key facts) comes first so the job can be understood
 * without opening the original (ADR-059).
 */
export function JobDetail({ detail, busy, onAction, onLinkDecision }: Props) {
  const evaluation = detail.evaluation
  const band = evaluation ? bandOf(evaluation.fit_band) : NOT_EVALUATED
  const possible = detail.sources.filter((s) => s.link_state === 'possible')
  const settled =
    detail.state === 'ignored' || detail.state === 'archived' || detail.state === 'applied'
  return (
    <article aria-label={detail.title} className="flex min-h-full flex-col bg-surface">
      <div className="border-b border-line px-5 pt-4 pb-3.5">
        <h2 className="mb-1 text-lg leading-snug font-semibold tracking-tight">{detail.title}</h2>
        <div className="text-ink-2">
          {detail.company_name}
          {detail.locations.length > 0 && ` · ${detail.locations.join('; ')}`}
        </div>
        <div className="mt-2.5 flex flex-wrap gap-1.5 text-xs">
          <span className="rounded-full border border-line-strong px-2 py-px">
            First seen {formatAge(detail.first_seen_at)} ago
          </span>
          {detail.is_shortlisted && (
            <span className="rounded-full bg-brand-soft px-2 py-px text-brand-text">
              ★ Shortlisted
            </span>
          )}
          {detail.closed && (
            <span className="rounded-full border border-line-strong px-2 py-px">
              No longer listed
            </span>
          )}
        </div>

        {evaluation ? (
          <div className="mt-3.5 flex items-center gap-3.5">
            <div className="text-[34px] leading-none font-bold tracking-tight tabular-nums">
              {evaluation.fit_score}
              <small className="text-base font-semibold text-ink-3">/100</small>
            </div>
            <div className="flex-1">
              <div
                className={cn(
                  'mb-1.5 inline-block rounded-md px-2 py-px text-xs font-semibold',
                  TONE_CLASSES[band.tone].soft,
                )}
              >
                {band.label}
              </div>
              <div
                role="meter"
                aria-label="Fit score"
                aria-valuenow={evaluation.fit_score}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuetext={`${evaluation.fit_score} out of 100, ${band.label}`}
                className="h-2 w-full overflow-hidden rounded-full bg-surface-3"
              >
                <span
                  className={cn('block h-full rounded-full', TONE_CLASSES[band.tone].fill)}
                  style={{ width: `${evaluation.fit_score}%` }}
                />
              </div>
            </div>
          </div>
        ) : (
          <div className="mt-3.5">
            <span className="rounded-md bg-band-bg px-2 py-px text-xs font-semibold text-band">
              {NOT_EVALUATED.label}
            </span>
            <p className="mt-2 text-sm text-ink-2">
              This job has not been scored yet: AI evaluation is off or the job is waiting its turn.
              You can still read it and decide manually.
            </p>
          </div>
        )}

        {evaluation && evaluation.gates.length > 0 && (
          <div className="mt-3 rounded-md bg-bad-bg px-3 py-2 text-sm text-bad">
            <strong>Hard constraints</strong>
            <ul className="mt-1 list-disc pl-5">
              {evaluation.gates.map((gate) => (
                <li key={gate.code}>{gate.reason}</li>
              ))}
            </ul>
          </div>
        )}
        {settled && (
          <p className="mt-3 rounded-md bg-surface-2 px-3 py-2 text-sm text-ink-2">
            This job is <strong>{detail.state}</strong>
            {detail.state === 'applied' && detail.applied_at
              ? ` (application recorded ${formatDateTime(detail.applied_at)})`
              : ''}
            .
          </p>
        )}
        {detail.last_change && (
          <p className="mt-3 rounded-md bg-caution-bg px-3 py-2 text-sm text-caution">
            <strong>Updated:</strong> {detail.last_change.changed_fields.join(', ')}
          </p>
        )}
      </div>

      <JobBrief brief={detail.brief} jobPostingId={detail.job_posting_id} />

      {evaluation && (
        <section className="border-b border-line px-5 py-4" aria-label="Why this score">
          <h3 className="mb-2 text-xs font-semibold tracking-wider text-ink-3 uppercase">
            Why this score{' '}
            <span className="font-normal tracking-normal normal-case">
              · hover or focus a row to see the posting&apos;s words
            </span>
          </h3>
          <DimensionList dimensions={detail.dimensions} />
          <AssessDirections jobPostingId={detail.job_posting_id} dimensions={detail.dimensions} />
          <p className="mt-2 text-xs text-ink-3">
            Unknown facts add nothing to the score. Policy {evaluation.policy_version}.
          </p>
        </section>
      )}

      <section className="border-b border-line px-5 py-3" aria-label="Where this job was seen">
        <h3 className="mb-2 text-xs font-semibold tracking-wider text-ink-3 uppercase">
          Where this job was seen ({detail.sources.length})
        </h3>
        <ul className="flex flex-col gap-1.5 text-sm">
          {detail.sources.map((source, index) => (
            <li key={source.job_posting_id} className="flex flex-wrap items-center gap-2">
              <a href={source.url} target="_blank" rel="noopener noreferrer" className="underline">
                {source.source_name}
              </a>
              {index === 0 && (
                <span className="rounded-full border border-line-strong px-2 text-xs">primary</span>
              )}
              {source.link_state === 'confirmed' && (
                <span className="text-xs text-ink-3">confirmed same job</span>
              )}
              {source.closed && <span className="text-xs text-ink-3">no longer listed</span>}
            </li>
          ))}
        </ul>
        {possible.map((source) => (
          <div
            key={source.job_opportunity_link_id}
            className="mt-2 rounded-md bg-caution-bg px-3 py-2 text-sm text-caution"
          >
            <p>
              {source.source_name} may be the same job ({Math.round(source.similarity * 100)}%
              similar).
            </p>
            <div className="mt-1.5 flex gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => onLinkDecision(source.job_opportunity_link_id, 'confirm')}
              >
                Same job
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => onLinkDecision(source.job_opportunity_link_id, 'reject')}
              >
                Different job
              </Button>
            </div>
          </div>
        ))}
      </section>

      <section className="flex-1 px-5 py-3" aria-label="Description">
        <details>
          <summary className="cursor-pointer text-sm text-ink-2">Full description</summary>
          <p className="mt-2 text-sm whitespace-pre-line">{detail.description_text}</p>
        </details>
      </section>

      <ActionBar detail={detail} busy={busy} onAction={onAction} />
    </article>
  )
}
