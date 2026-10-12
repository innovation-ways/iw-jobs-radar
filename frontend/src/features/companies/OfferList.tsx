import { useState } from 'react'
import { formatAge } from '@/lib/format'
import { cn } from '@/lib/utils'
import { bandOf, NOT_EVALUATED, TONE_CLASSES } from '@/features/inbox/bands'
import { Button } from '@/components/ui/button'
import { describeApiError } from '@/api/errors'
import { ACTION_MESSAGES, undoPlan, type InboxState, type OwnerAction } from '@/features/inbox/undo'
import { useOfferActions, type Offer } from './queries'

type Toggle = 'open' | 'closed' | 'recommended' | 'hideIgnored' | 'older'

/** Bands at or above the default relevance threshold (45) that are not gated. */
const RECOMMENDED = new Set(['excellent', 'strong', 'average'])

function visible(offer: Offer, on: Record<Toggle, boolean>): boolean {
  if (offer.closed ? !on.closed : !on.open) return false
  if (on.recommended && !(offer.fit_band && RECOMMENDED.has(offer.fit_band))) return false
  if (on.hideIgnored && offer.state === 'ignored') return false
  return true
}

type SortKey = 'newest' | 'oldest' | 'best' | 'worst'

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: 'newest', label: 'Newest first' },
  { value: 'oldest', label: 'Oldest first' },
  { value: 'best', label: 'Highest fit' },
  { value: 'worst', label: 'Lowest fit' },
]

/**
 * Order offers by age (`first_seen_at`) or fit score. Offers without a score always come last
 * for the fit orders, and ties fall back to the newest first. Returns a new array.
 */
function sorted(offers: Offer[], key: SortKey): Offer[] {
  const time = (o: Offer) => Date.parse(o.first_seen_at)
  const byNewest = (a: Offer, b: Offer) => time(b) - time(a)
  const byFit = (direction: 1 | -1) => (a: Offer, b: Offer) => {
    if (a.fit_score === null || b.fit_score === null) {
      return a.fit_score === b.fit_score ? byNewest(a, b) : a.fit_score === null ? 1 : -1
    }
    return (b.fit_score - a.fit_score) * direction || byNewest(a, b)
  }
  const compare = {
    newest: byNewest,
    oldest: (a: Offer, b: Offer) => time(a) - time(b),
    best: byFit(1),
    worst: byFit(-1),
  }[key]
  return [...offers].sort(compare)
}

/** What the Undo button needs to take the last action back. */
interface LastAction {
  itemId: number
  action: OwnerAction
  previous: InboxState
  version: number
  message: string
}

/**
 * The triage buttons of one offer, the same actions as the Inbox detail: shortlist, ignore,
 * archive, mark applied, and Restore once the offer is ignored, archived or applied. Every label
 * names the offer, so a list of identical buttons stays understandable to a screen reader.
 */
function OfferActions({
  offer,
  busy,
  onAction,
}: {
  offer: Offer
  busy: boolean
  onAction: (action: OwnerAction) => void
}) {
  const settled = ['ignored', 'archived', 'applied'].includes(offer.state ?? '')
  return (
    <div className="col-span-full flex flex-wrap gap-1.5">
      <Button
        size="sm"
        variant="outline"
        disabled={busy}
        aria-pressed={offer.is_shortlisted}
        aria-label={`${offer.is_shortlisted ? 'Remove' : 'Add'} ${offer.title} ${offer.is_shortlisted ? 'from' : 'to'} shortlist`}
        onClick={() => onAction(offer.is_shortlisted ? 'unshortlist' : 'shortlist')}
      >
        <span aria-hidden="true">{offer.is_shortlisted ? '★' : '☆'}</span> Shortlist
      </Button>
      {settled ? (
        <Button
          size="sm"
          disabled={busy}
          aria-label={`Restore ${offer.title}`}
          onClick={() => onAction('restore')}
        >
          ↩ Restore
        </Button>
      ) : (
        <>
          <Button
            size="sm"
            variant="outline"
            disabled={busy}
            aria-label={`Ignore ${offer.title}`}
            onClick={() => onAction('ignore')}
          >
            Ignore
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={busy}
            aria-label={`Archive ${offer.title}`}
            onClick={() => onAction('archive')}
          >
            Archive
          </Button>
          <Button
            size="sm"
            variant="ghost"
            disabled={busy}
            aria-label={`Mark ${offer.title} as applied`}
            onClick={() => onAction('record_application')}
          >
            Mark applied
          </Button>
        </>
      )}
    </div>
  )
}

function Row({
  offer,
  busy,
  onAction,
}: {
  offer: Offer
  busy: boolean
  onAction: (action: OwnerAction) => void
}) {
  const band = offer.fit_band ? bandOf(offer.fit_band) : NOT_EVALUATED
  const dim = offer.state === 'ignored' || offer.state === 'archived' || offer.closed
  const isNew = offer.state === 'unread' || offer.state === 'updated_unread'
  return (
    <li
      aria-label={offer.title}
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
      {/* Without an inbox item the owner has nothing to triage (the server has no state to move). */}
      {offer.job_inbox_item_id !== null && (
        <OfferActions offer={offer} busy={busy} onAction={onAction} />
      )}
    </li>
  )
}

/**
 * The offers of a company, in the Inbox's visual language: fit tile with band in words, triage
 * state, shortlist star and the Inbox's triage actions on every offer (with Undo); ignored and closed offers stay visible but dimmed. Filters are local;
 * "Older" asks the server for offers beyond the recency limit (`onOlderChange`).
 */
export function OfferList({
  offers,
  recencyDays,
  includeOlder,
  truncated,
  onOlderChange,
}: {
  offers: Offer[]
  /** The server cut the list: only the best-fitting offers are here. */
  truncated: boolean
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
  const [sortKey, setSortKey] = useState<SortKey>('best')
  const act = useOfferActions()
  const [last, setLast] = useState<LastAction | null>(null)
  const [error, setError] = useState<string | null>(null)

  /** Perform one action on an offer and remember how to take it back. */
  const perform = async (offer: Offer, action: OwnerAction) => {
    if (offer.job_inbox_item_id === null || offer.version === null) return
    setError(null)
    try {
      const result = await act.mutateAsync({
        itemId: offer.job_inbox_item_id,
        action,
        version: offer.version,
      })
      const previous = (offer.state ?? 'read') as InboxState
      setLast(
        undoPlan(action, previous).length
          ? {
              itemId: offer.job_inbox_item_id,
              action,
              previous,
              version: result.item.version,
              message: `${ACTION_MESSAGES[action]}: ${offer.title}`,
            }
          : null,
      )
    } catch (e) {
      setLast(null)
      setError(describeApiError(e).message)
    }
  }

  const undo = async () => {
    if (!last) return
    setLast(null)
    setError(null)
    let version = last.version
    try {
      for (const action of undoPlan(last.action, last.previous)) {
        const result = await act.mutateAsync({ itemId: last.itemId, action, version })
        version = result.item.version
      }
    } catch (e) {
      setError(describeApiError(e).message)
    }
  }

  const shown = sorted(
    offers.filter((o) => visible(o, on)),
    sortKey,
  )
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
        <label className="ml-auto flex items-center gap-1.5 text-xs text-ink-2">
          Sort by
          <select
            className="rounded-md border border-line-strong bg-surface px-2 py-0.5 text-xs"
            value={sortKey}
            onChange={(e) => setSortKey(e.target.value as SortKey)}
          >
            {SORT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      {truncated && (
        <p className="mb-2 text-xs text-ink-3">
          Showing the {offers.length} best-fitting offers of this company.
        </p>
      )}
      {error && (
        <p role="alert" className="mb-2 text-sm text-bad">
          {error}
        </p>
      )}
      {last && (
        <p role="status" className="mb-2 flex items-center gap-2 text-sm text-ink-2">
          {last.message}
          <Button size="sm" variant="outline" onClick={() => void undo()}>
            Undo
          </Button>
        </p>
      )}
      {shown.length === 0 ? (
        <p className="text-sm text-ink-2">
          {offers.length === 0
            ? `No offers from the last ${recencyDays} days.`
            : 'No offer matches these filters.'}
        </p>
      ) : (
        <ul className="text-sm">
          {shown.map((o) => (
            <Row
              key={o.job_opportunity_id}
              offer={o}
              busy={act.isPending}
              onAction={(action) => void perform(o, action)}
            />
          ))}
        </ul>
      )}
    </section>
  )
}
