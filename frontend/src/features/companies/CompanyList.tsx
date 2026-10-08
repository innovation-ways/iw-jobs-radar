import { cn } from '@/lib/utils'
import type { CompanySummary, WindowDays } from './queries'

/** The companies as a listbox; each row shows new and relevant offers in the chosen window. */
export function CompanyList({
  companies,
  window,
  selectedId,
  onSelect,
}: {
  companies: CompanySummary[]
  window: WindowDays
  selectedId: number | null
  onSelect: (id: number) => void
}) {
  return (
    <div role="listbox" aria-label="Companies" className="flex flex-col gap-1.5 p-2">
      {companies.map((c) => {
        const fresh = c[`new_offers_${window}d`]
        const relevant = c[`relevant_new_offers_${window}d`]
        return (
          <div
            key={c.company_id}
            role="option"
            aria-selected={c.company_id === selectedId}
            tabIndex={0}
            onClick={() => onSelect(c.company_id)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault()
                onSelect(c.company_id)
              }
            }}
            className={cn(
              'flex cursor-pointer items-center justify-between gap-2 rounded-md border bg-surface px-3 py-2',
              c.company_id === selectedId
                ? 'border-brand ring-1 ring-brand'
                : 'border-line hover:border-line-strong',
            )}
          >
            <span className="min-w-0 truncate font-medium">{c.name}</span>
            <span className="flex shrink-0 gap-2 text-xs tabular-nums text-ink-2">
              <span>{fresh} new</span>
              {relevant > 0 && (
                <span className="font-semibold text-brand-text">{relevant} relevant</span>
              )}
            </span>
          </div>
        )
      })}
    </div>
  )
}
