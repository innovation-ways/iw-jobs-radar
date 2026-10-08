import { useState } from 'react'
import { useSearchParams } from 'react-router'
import { Button } from '@/components/ui/button'
import { CompanyList } from '@/features/companies/CompanyList'
import { DossierPanel } from '@/features/companies/DossierPanel'
import { useCompanies, type WindowDays } from '@/features/companies/queries'

const WINDOWS: WindowDays[] = [7, 15, 30]
const PAGE = 50

/**
 * Companies: every company with its new offers in the last 7, 15 or 30 days (and how many are
 * relevant to the search intent), and the dossier of the selected one. Selection is kept in the
 * address (`?company=`) so other screens can link to a company.
 */
export function Companies() {
  const [params, setParams] = useSearchParams()
  const [q, setQ] = useState('')
  const [window, setWindow] = useState<WindowDays>(15)
  const [relevantOnly, setRelevantOnly] = useState(false)
  const [limit, setLimit] = useState(PAGE)
  const { data, isPending, isError, refetch } = useCompanies({ q, window, relevantOnly, limit })
  const selected = Number(params.get('company')) || null

  return (
    <div className="grid min-h-full grid-cols-[minmax(280px,360px)_1fr]">
      <div className="flex flex-col border-r border-line">
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
          <div className="flex items-center gap-2 text-xs text-ink-2">
            New offers in the last
            <span role="group" aria-label="Period" className="flex gap-1">
              {WINDOWS.map((days) => (
                <button
                  key={days}
                  type="button"
                  aria-pressed={window === days}
                  onClick={() => setWindow(days)}
                  className={`rounded-md border px-2 py-1 ${window === days ? 'border-brand bg-brand-soft text-brand-text' : 'border-line-strong'}`}
                >
                  {days} d
                </button>
              ))}
            </span>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={relevantOnly}
              onChange={(e) => setRelevantOnly(e.target.checked)}
            />
            Only offers relevant to my profile
          </label>
          {data && <p className="text-xs text-ink-3">{data.total} companies</p>}
        </div>
        <div className="flex-1 overflow-y-auto">
          {isPending && <p className="p-4 text-ink-3">Loading…</p>}
          {isError && (
            <div role="alert" className="flex items-center gap-3 p-4 text-bad">
              Could not load the companies.
              <Button variant="outline" size="sm" onClick={() => void refetch()}>
                Try again
              </Button>
            </div>
          )}
          {data && data.items.length === 0 && (
            <p className="p-4 text-sm text-ink-2">
              {q || relevantOnly
                ? 'No company matches.'
                : 'No companies yet. Companies appear when you add a job board in Sources.'}
            </p>
          )}
          {data && data.items.length > 0 && (
            <CompanyList
              companies={data.items}
              window={window}
              selectedId={selected}
              onSelect={(id) => setParams({ company: String(id) })}
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
      <div className="overflow-y-auto">
        {selected ? (
          <DossierPanel key={selected} companyId={selected} />
        ) : (
          <p className="p-6 text-ink-2">Select a company to see its dossier.</p>
        )}
      </div>
    </div>
  )
}
