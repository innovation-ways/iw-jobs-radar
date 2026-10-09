import { useState } from 'react'
import { describeApiError } from '@/api/errors'
import { Button } from '@/components/ui/button'
import { BoardFiltersFields } from './BoardFiltersFields'
import { DEFAULT_FILTERS, filtersProblem, withDefaults } from './filters'
import type { JobBoardFilters, SourceRead, useJobBoardActions } from './queries'

type Actions = ReturnType<typeof useJobBoardActions>

/**
 * The filters of a company board, off by default: every posting of the company is kept. When the
 * owner opts in, only postings in the chosen technology areas and inside the owner's reach (taken
 * from the profile and the search intents) are stored, which keeps a large company from filling
 * the inbox. Saved with the version the owner saw.
 */
export function CompanyBoardFilters({ source, actions }: { source: SourceRead; actions: Actions }) {
  const saved = source.filters ? withDefaults(source.filters) : null
  const [enabled, setEnabled] = useState(saved !== null)
  const [draft, setDraft] = useState<JobBoardFilters>(saved ?? DEFAULT_FILTERS)
  const problem = enabled ? filtersProblem(draft) : null
  const dirty = enabled
    ? saved === null || JSON.stringify(saved) !== JSON.stringify(draft)
    : saved !== null
  const pending = actions.saveFilters.isPending || actions.clearFilters.isPending
  const failed = actions.saveFilters.isError
    ? actions.saveFilters.error
    : actions.clearFilters.isError
      ? actions.clearFilters.error
      : null
  const id = source.source_configuration_id

  function save() {
    if (enabled) actions.saveFilters.mutate({ id, version: source.version, filters: draft })
    else actions.clearFilters.mutate({ id, version: source.version })
  }

  return (
    <div className="flex flex-col gap-3 border-t border-line bg-surface-2 px-4 py-4 text-sm">
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(event) => setEnabled(event.target.checked)}
        />
        Keep only postings that match my areas and location
      </label>
      {enabled ? (
        <>
          <BoardFiltersFields
            value={draft}
            categories={DEFAULT_FILTERS.categories}
            onChange={setDraft}
            idPrefix={`company-${id}`}
          />
          <p className="text-xs text-ink-3">
            Location comes from your profile and search intents: remote work open to your countries,
            and on-site or hybrid work inside your radius. A place that cannot be read is kept.
          </p>
        </>
      ) : (
        <p className="text-xs text-ink-3">Filters are off: every posting is kept.</p>
      )}
      <div className="flex flex-wrap items-center gap-3">
        <Button size="sm" disabled={!dirty || problem !== null || pending} onClick={save}>
          Save filters
        </Button>
        <span className="text-xs text-ink-3">
          Applies from the next run. Postings already kept are not closed by a new filter.
        </span>
      </div>
      {failed && (
        <p role="alert" className="text-sm text-bad">
          {describeApiError(failed).message}
        </p>
      )}
    </div>
  )
}
