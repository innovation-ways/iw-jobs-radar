import { useState } from 'react'
import { formatAge } from '@/lib/format'
import { cn } from '@/lib/utils'
import { bandOf, NOT_EVALUATED, TONE_CLASSES } from '@/features/inbox/bands'
import type { Offer } from './queries'

type Toggle = 'open' | 'closed' | 'recommended' | 'hideIgnored' | 'older'

/** Bands at or above the default relevance threshold (45) that are not gated. */
const RECOMMENDED = new Set(['excellent', 'strong', 'average'])

function visible(offer: Offer, on: Record<Toggle, boolean>): boolean {
  if (offer.closed ? !on.closed : !on.open) return false
  if (on.recommended && !(offer.fit_band && RECOMMENDED.has(offer.fit_band))) return false
  if (on.hideIgnored && offer.state === 'ignored') return false
  return true
}

function Row({ offer }: { offer: Offer }) {
  const band = offer.fit_band ? bandOf(offer.fit_band) : NOT_EVALUATED
  const dim = offer.state === 'ignored' || offer.state === 'archived' || offer.closed
  const isNew = offer.state === 'unread' || offer.state === 'updated_unread'
  return (
    <li
      className={cn(
        'grid grid-cols-[56px_minmax(0,1fr)_auto] items-center gap-3 border-t border-line py-2 first:border-t-0',
        dim && 'opacity-60',
      )}
    >
      <div className={cn('rounded-lg py-1 text-center', TONE_CLASSES[band.tone].soft)}>
        <div className="text-lg leading-tight font-bold tabular-nums">{offer.fit_score ?? '—'}</div>
        <div className="text-[11px] leading-tight font-semibold">{band.short}</div>
      </div>
      <div className="min-w-0">
        <div className="flex items-center gap-1.5 font-semibold">
          {offer.is_shortlisted && (
            <span aria-label="Shortlisted" className="text-caution">
              ★
            </span>
          )}
          <a
            className="truncate underline"
            href={offer.source_url}
            target="_blank"
            rel="noreferrer noopener"
          >
            {offer.title}
          </a>
          {isNew && (
            <span className="shrink-0 rounded bg-brand px-1.5 text-[11px] font-bold text-on-brand">
              {offer.state === 'updated_unread' ? 'UPDATED' : 'NEW'}
            </span>
          )}
        </div>
        <div className="text-xs text-ink-3 tabular-nums">{formatAge(offer.first_seen_at)} ago</div>
      </div>
      <div className="flex flex-col items-end gap-1 text-xs text-ink-2">
        {offer.closed && (
          <span className="rounded-full border border-line-strong px-2">Closed</span>
        )}
        {offer.state && ['ignored', 'archived', 'applied'].includes(offer.state) && (
          <span className="rounded-full border border-line-strong px-2">{offer.state}</span>
        )}
      </div>
    </li>
  )
}

/**
 * The offers of a company, in the Inbox's visual language: fit tile with band in words, triage
 * state, shortlist star; ignored and closed offers stay visible but dimmed. Filters are local;
 * "Older" asks the server for offers beyond the recency limit (`onOlderChange`).
 */
export function OfferList({
  offers,
  recencyDays,
  includeOlder,
  onOlderChange,
}: {
  offers: Offer[]
  recencyDays: number
  includeOlder: boolean
  onOlderChange: (value: boolean) => void
}) {
  const [on, setOn] = useState<Record<Toggle, boolean>>({
    open: true,
    closed: false,
    recommended: false,
    hideIgnored: false,
    older: includeOlder,
  })
  const flip = (key: Toggle) => {
    setOn({ ...on, [key]: !on[key] })
    if (key === 'older') onOlderChange(!on.older)
  }
  const shown = offers.filter((o) => visible(o, on))
  const chip = (key: Toggle, label: string) => (
    <button
      key={key}
      type="button"
      aria-pressed={on[key]}
      onClick={() => flip(key)}
      className={`rounded-full border px-2.5 py-0.5 text-xs ${on[key] ? 'border-brand bg-brand-soft font-semibold text-brand-text' : 'border-line-strong text-ink-2'}`}
    >
      {label}
    </button>
  )
  return (
    <section aria-labelledby="offers" className="rounded-lg border border-line bg-surface p-4">
      <h3 id="offers" className="mb-2 text-sm font-semibold">
        Offers ({shown.length})
      </h3>
      <div role="group" aria-label="Offer filters" className="mb-2 flex flex-wrap gap-1.5">
        {chip('open', 'Open')}
        {chip('closed', 'Closed')}
        {chip('recommended', 'Recommended')}
        {chip('hideIgnored', 'Hide ignored')}
        {chip('older', `Older than ${recencyDays} days`)}
      </div>
      {shown.length === 0 ? (
        <p className="text-sm text-ink-2">
          {offers.length === 0
            ? `No offers from the last ${recencyDays} days.`
            : 'No offer matches these filters.'}
        </p>
      ) : (
        <ul className="text-sm">
          {shown.map((o) => (
            <Row key={o.job_opportunity_id} offer={o} />
          ))}
        </ul>
      )}
    </section>
  )
}
