import { ChipsInput } from '@/components/ChipsInput'
import { filtersProblem } from './filters'
import type { JobBoardFilters } from './queries'

const FIELD = 'rounded-md border border-line-strong bg-surface px-2.5 py-1.5 text-sm text-ink'

/**
 * The filters an owner can set on a job board: technology areas, search terms, how recent a posting
 * must be and the most postings kept per run. The countries are not here: they come from the
 * profile and the search intents.
 *
 * @param value the current filters
 * @param categories the technology areas the board offers
 * @param onChange called with the edited filters
 * @param idPrefix keeps the field ids unique when several boards are on the page
 */
export function BoardFiltersFields({
  value,
  categories,
  onChange,
  idPrefix,
}: {
  value: JobBoardFilters
  categories: string[]
  onChange: (next: JobBoardFilters) => void
  idPrefix: string
}) {
  const problem = filtersProblem(value)
  return (
    <div className="flex flex-col gap-3">
      <fieldset>
        <legend className="text-xs text-ink-2">Technology areas</legend>
        <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1.5">
          {categories.map((category) => (
            <label key={category} className="flex items-center gap-1.5 text-sm">
              <input
                type="checkbox"
                checked={value.categories.includes(category)}
                onChange={(event) =>
                  onChange({
                    ...value,
                    categories: event.target.checked
                      ? [...value.categories, category]
                      : value.categories.filter((item) => item !== category),
                  })
                }
              />
              {category}
            </label>
          ))}
        </div>
      </fieldset>
      <ChipsInput
        label="Search terms (optional)"
        values={value.search_terms}
        onChange={(search_terms) => onChange({ ...value, search_terms })}
        placeholder="For example python"
      />
      <div className="flex flex-wrap gap-3">
        <label htmlFor={`${idPrefix}-age`} className="flex flex-col gap-1 text-xs text-ink-2">
          Posted within (days)
          <input
            id={`${idPrefix}-age`}
            type="number"
            min={1}
            max={365}
            value={value.max_age_days || ''}
            onChange={(event) => onChange({ ...value, max_age_days: Number(event.target.value) })}
            className={`${FIELD} w-28`}
          />
        </label>
        <label htmlFor={`${idPrefix}-limit`} className="flex flex-col gap-1 text-xs text-ink-2">
          Most postings per run
          <input
            id={`${idPrefix}-limit`}
            type="number"
            min={1}
            max={5000}
            value={value.max_postings_per_run || ''}
            onChange={(event) =>
              onChange({ ...value, max_postings_per_run: Number(event.target.value) })
            }
            className={`${FIELD} w-32`}
          />
        </label>
      </div>
      {problem && (
        <p role="alert" className="text-sm text-bad">
          {problem}
        </p>
      )}
    </div>
  )
}
