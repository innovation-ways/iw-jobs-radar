import { cn } from '@/lib/utils'
import type { CompanySummary } from './queries'

/**
 * A star button that follows or unfollows a company. It reports state with `aria-pressed` and
 * a label that names the company; the filled star is never the only cue (the label changes too).
 */
export function FollowStar({
  name,
  followed,
  disabled,
  onToggle,
  size = 'sm',
}: {
  name: string
  followed: boolean
  disabled?: boolean
  onToggle: () => void
  size?: 'sm' | 'lg'
}) {
  return (
    <button
      type="button"
      aria-pressed={followed}
      aria-label={`${followed ? 'Unfollow' : 'Follow'} ${name}`}
      title={followed ? 'Unfollow' : 'Follow'}
      disabled={disabled}
      onClick={(event) => {
        event.stopPropagation() // the row itself selects the company
        onToggle()
      }}
      className={cn(
        'rounded p-0.5 leading-none hover:bg-surface-2',
        size === 'lg' ? 'text-2xl' : 'text-base',
        followed ? 'text-caution' : 'text-ink-3 hover:text-caution',
      )}
    >
      <span aria-hidden="true">{followed ? '★' : '☆'}</span>
    </button>
  )
}

function Row({
  company: c,
  selected,
  onSelect,
  onToggleFollow,
}: {
  company: CompanySummary
  selected: boolean
  onSelect: () => void
  onToggleFollow: () => void
}) {
  const quiet = c.open_offers === 0
  return (
    <div
      role="option"
      aria-selected={selected}
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(e) => {
        if (e.target !== e.currentTarget) return // keys on the star belong to the star
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onSelect()
        }
      }}
      className={cn(
        'grid cursor-pointer grid-cols-[24px_minmax(0,1fr)_auto] items-center gap-2 rounded-md border bg-surface px-2.5 py-2',
        selected ? 'border-brand ring-1 ring-brand' : 'border-line hover:border-line-strong',
      )}
    >
      <FollowStar name={c.name} followed={c.is_followed} onToggle={onToggleFollow} />
      <div className="min-w-0">
        <div
          className={cn(
            'flex items-center gap-1.5 truncate',
            quiet ? 'text-ink-2' : 'font-semibold',
          )}
        >
          <span className="truncate">{c.name}</span>
          {c.pending_candidates > 0 && (
            <span className="shrink-0 rounded-full bg-surface-2 px-2 text-xs font-normal text-ink-2">
              Identify
            </span>
          )}
        </div>
        <div className="text-xs text-ink-2 tabular-nums">
          {quiet ? 'No open offers' : `${c.open_offers} open`}
          {c.recommended_offers > 0 && (
            <span className="font-semibold text-brand-text">
              {' · '}
              {c.recommended_offers} recommended
            </span>
          )}
        </div>
      </div>
      <span className="text-right text-sm font-semibold tabular-nums">
        {c.best_fit_score !== null ? (
          <span aria-label={`Best fit ${c.best_fit_score}`}>{c.best_fit_score}</span>
        ) : (
          <span className="text-xs font-normal text-ink-3">{quiet ? '—' : 'Not evaluated'}</span>
        )}
      </span>
    </div>
  )
}

/**
 * The companies as a listbox, followed ones in their own group on top. Each row shows the counted
 * offers (open, recommended), the best fit and whether the company still needs identifying.
 */
export function CompanyList({
  companies,
  selectedId,
  onSelect,
  onToggleFollow,
}: {
  companies: CompanySummary[]
  selectedId: number | null
  onSelect: (id: number) => void
  onToggleFollow: (company: CompanySummary) => void
}) {
  const followed = companies.filter((c) => c.is_followed)
  const others = companies.filter((c) => !c.is_followed)
  const rows = (list: CompanySummary[]) =>
    list.map((c) => (
      <Row
        key={c.company_id}
        company={c}
        selected={c.company_id === selectedId}
        onSelect={() => onSelect(c.company_id)}
        onToggleFollow={() => onToggleFollow(c)}
      />
    ))
  return (
    <div role="listbox" aria-label="Companies" className="flex flex-col gap-1.5 p-2">
      {followed.length > 0 && (
        <>
          <div
            role="presentation"
            className="px-1 pt-1 text-[11px] font-semibold tracking-wider text-ink-3 uppercase"
          >
            Followed
          </div>
          {rows(followed)}
        </>
      )}
      {followed.length > 0 && others.length > 0 && (
        <div
          role="presentation"
          className="px-1 pt-2 text-[11px] font-semibold tracking-wider text-ink-3 uppercase"
        >
          All companies
        </div>
      )}
      {rows(others)}
    </div>
  )
}
