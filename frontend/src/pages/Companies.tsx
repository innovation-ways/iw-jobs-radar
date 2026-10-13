import { ArrowLeft } from 'lucide-react'
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { Button } from '@/components/ui/button'
import { CompanyList } from '@/features/companies/CompanyList'
import { DossierPanel } from '@/features/companies/DossierPanel'
import { useCompanies, useFollow, type CompanySort } from '@/features/companies/queries'
import { cn } from '@/lib/utils'

const PAGE = 50

type FilterKey = 'open' | 'recommended' | 'pending'
const FILTERS: { key: FilterKey; label: string }[] = [
  { key: 'open', label: 'With open offers' },
  { key: 'recommended', label: 'Recommended' },
  { key: 'pending', label: 'Needs identification' },
]

/**
 * Companies: the companies seen in job postings, followed ones first, then by the newest offers
 * (or the owner's chosen order; ADR-053). Ignored companies leave
 * the main list and wait in a third group at the end (ADR-061). Filters narrow the list; "With
 * open offers" is on by default and never hides a followed company. Selection is kept in the address (`?company=`) so other screens
 * can link to a company.
 */
export function Companies() {
  const [params, setParams] = useSearchParams()
  const [q, setQ] = useState('')
  const [filters, setFilters] = useState<Record<FilterKey, boolean>>({
    open: true,
    recommended: false,
    pending: false,
  })
  const [sort, setSort] = useState<CompanySort>('newest')
  const [limit, setLimit] = useState(PAGE)
  const follow = useFollow()
  const { data, isPending, isError, refetch } = useCompanies({
    q,
    sort,
    hideIgnored: true,
    openOnly: filters.open,
    recommendedOnly: filters.recommended,
    pendingOnly: filters.pending,
    limit,
  })
  // The ignored companies are a separate query: the filters that narrow the main list (open
  // offers, recommended) say nothing about a company the owner has set aside.
  const ignoredList = useCompanies({
    q,
    sort,
    hideIgnored: false,
    ignoredOnly: true,
    openOnly: false,
    recommendedOnly: false,
    pendingOnly: false,
    limit: 200,
  })
  const ignoredItems = ignoredList.data?.items ?? []
  const selected = Number(params.get('company')) || null
  // Below `lg` only one pane fits; a link with ?company= opens straight on the dossier.
  const [mobileView, setMobileView] = useState<'list' | 'detail'>(selected ? 'detail' : 'list')
  const filtered = q !== '' || filters.recommended || filters.pending

  return (
    <div
      data-mobile-view={mobileView}
      className="grid h-full min-h-0 grid-cols-1 lg:grid-cols-[minmax(300px,400px)_1fr]"
    >
      <div
        className={cn(
          'flex min-h-0 flex-col border-r border-line',
          mobileView === 'detail' && 'max-lg:hidden',
        )}
      >
        <div className="flex flex-col gap-2.5 border-b border-line bg-surface p-3">
          <input
            type="search"
            aria-label="Search companies"
            placeholder="Search companies…"
            value={q}
            onChange={(e) => {
              setQ(e.target.value)
              setLimit(PAGE)
            }}
            className="rounded-md border border-line-strong bg-surface px-2.5 py-1.5 text-sm"
          />
          <div role="group" aria-label="Filters" className="flex flex-wrap gap-1.5">
            {FILTERS.map(({ key, label }) => (
              <button
                key={key}
                type="button"
                aria-pressed={filters[key]}
                onClick={() => {
                  setFilters({ ...filters, [key]: !filters[key] })
                  setLimit(PAGE)
                }}
                className={`rounded-full border px-2.5 py-0.5 text-xs ${filters[key] ? 'border-brand bg-brand-soft font-semibold text-brand-text' : 'border-line-strong text-ink-2'}`}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2">
            <label className="flex items-center gap-1.5 text-xs text-ink-2">
              Sort by
              <select
                aria-label="Sort companies by"
                value={sort}
                onChange={(e) => {
                  setSort(e.target.value as CompanySort)
                  setLimit(PAGE)
                }}
                className="rounded-md border border-line-strong bg-surface px-2 py-1 text-xs"
              >
                <option value="newest">Newest offers</option>
                <option value="recommended">Most recommended offers</option>
                <option value="fit">Best fit</option>
                <option value="name">Name</option>
              </select>
            </label>
          </div>
          {data && (
            <p className="text-xs text-ink-3">
              {data.total} companies · counting open offers from the last {data.recency_days} days,
              without the ones you ignored.{' '}
              <Link to="/sources" className="underline">
                Change the limit
              </Link>
            </p>
          )}
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">
          {isPending && <p className="p-4 text-ink-3">Loading…</p>}
          {isError && (
            <div role="alert" className="flex items-center gap-3 p-4 text-bad">
              Could not load the companies.
              <Button variant="outline" size="sm" onClick={() => void refetch()}>
                Try again
              </Button>
            </div>
          )}
          {follow.isError && (
            <p role="alert" className="p-3 text-sm text-bad">
              Could not change the follow state. Try again.
            </p>
          )}
          {data && data.items.length === 0 && ignoredItems.length === 0 && (
            <p className="p-4 text-sm text-ink-2">
              {filtered
                ? 'No company matches.'
                : filters.open
                  ? 'No company has open offers. Turn off "With open offers" to see them all.'
                  : 'No companies yet. Companies appear when you add a job board in Sources.'}
            </p>
          )}
          {data && (data.items.length > 0 || ignoredItems.length > 0) && (
            <CompanyList
              companies={data.items}
              ignored={ignoredItems}
              selectedId={selected}
              onSelect={(id) => {
                setParams({ company: String(id) })
                setMobileView('detail')
              }}
              onToggleFollow={(c) =>
                follow.mutate({ companyId: c.company_id, follow: !c.is_followed })
              }
            />
          )}
          {data && data.items.length < data.total && (
            <div className="p-3">
              <Button variant="outline" size="sm" onClick={() => setLimit(limit + PAGE)}>
                Show more
              </Button>
            </div>
          )}
        </div>
      </div>
      <div className={cn('min-h-0 overflow-y-auto', mobileView === 'list' && 'max-lg:hidden')}>
        <div className="sticky top-0 z-[5] border-b border-line bg-surface px-3 py-1.5 lg:hidden">
          <Button variant="ghost" size="sm" onClick={() => setMobileView('list')}>
            <ArrowLeft aria-hidden="true" />
            Back to the list
          </Button>
        </div>
        {selected ? (
          <DossierPanel key={selected} companyId={selected} recencyDays={data?.recency_days} />
        ) : (
          <p className="p-6 text-ink-2">Select a company to see its dossier.</p>
        )}
      </div>
    </div>
  )
}
