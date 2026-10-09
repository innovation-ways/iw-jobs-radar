import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { describeApiError } from '@/api/errors'
import { BoardCredentialField } from './BoardCredentialField'
import { BoardFiltersFields } from './BoardFiltersFields'
import { filtersProblem, withDefaults } from './filters'
import { useCatalogue, useJobBoardActions, type JobBoardFilters, type SourceRead } from './queries'

type Actions = ReturnType<typeof useJobBoardActions>

const FALLBACK_CATEGORIES = ['software', 'data', 'devops', 'security', 'telecom']

function sameFilters(a: JobBoardFilters, b: JobBoardFilters): boolean {
  return JSON.stringify(a) === JSON.stringify(b)
}

/**
 * The second disclosure level of a job board row: its filters, its key (if it needs one) and what
 * the board asks for in return (terms and attribution). Changes are saved with the version the
 * owner saw, so a stale screen is reported instead of overwriting.
 */
export function BoardSettings({ source, actions }: { source: SourceRead; actions: Actions }) {
  const catalogue = useCatalogue()
  const entry = catalogue.data?.find((item) => item.catalogue_key === source.external_identifier)
  const saved = withDefaults(source.filters)
  const [draft, setDraft] = useState<JobBoardFilters>(saved)
  const problem = filtersProblem(draft)
  const dirty = !sameFilters(draft, saved)
  const keyError = [actions.writeKey, actions.removeKey].find((m) => m.isError)?.error
  const filtersError = actions.saveFilters.isError
    ? describeApiError(actions.saveFilters.error).message
    : null

  return (
    <div className="flex flex-col gap-4 border-t border-line bg-surface-2 px-4 py-4 text-sm">
      <section aria-label={`Filters for ${source.display_name}`} className="flex flex-col gap-3">
        <h3 className="text-xs font-semibold tracking-wider text-ink-3 uppercase">Filters</h3>
        <BoardFiltersFields
          value={draft}
          categories={entry?.available_categories ?? FALLBACK_CATEGORIES}
          onChange={setDraft}
          idPrefix={`settings-${source.source_configuration_id}`}
        />
        <div className="flex flex-wrap items-center gap-3">
          <Button
            size="sm"
            disabled={!dirty || problem !== null || actions.saveFilters.isPending}
            onClick={() =>
              actions.saveFilters.mutate({
                id: source.source_configuration_id,
                version: source.version,
                filters: draft,
              })
            }
          >
            Save filters
          </Button>
          <span className="text-xs text-ink-3">
            Applies from the next run. Postings already kept are not closed by a new filter.
          </span>
        </div>
        {filtersError && (
          <p role="alert" className="text-sm text-bad">
            {filtersError}
          </p>
        )}
      </section>

      {source.credential_status !== 'not_needed' && (
        <section aria-label={`Key for ${source.display_name}`}>
          <h3 className="mb-2 text-xs font-semibold tracking-wider text-ink-3 uppercase">Key</h3>
          <BoardCredentialField
            label={entry?.credential_label ?? 'API key'}
            saved={source.credential_status === 'saved'}
            updatedAt={source.credential_updated_at}
            busy={actions.writeKey.isPending || actions.removeKey.isPending}
            onSave={(secret, done) =>
              actions.writeKey.mutate(
                { id: source.source_configuration_id, secret },
                { onSuccess: done },
              )
            }
            onRemove={() => actions.removeKey.mutate(source.source_configuration_id)}
          />
          {keyError && (
            <p role="alert" className="mt-2 text-sm text-bad">
              {describeApiError(keyError).message}
            </p>
          )}
        </section>
      )}

      <section aria-label={`About ${source.display_name}`} className="flex flex-col gap-1">
        <h3 className="text-xs font-semibold tracking-wider text-ink-3 uppercase">Source</h3>
        {source.attribution_text && <p>{source.attribution_text}</p>}
        {entry?.delay_note && <p className="text-ink-2">{entry.delay_note}</p>}
        {entry && (
          <p className="text-ink-2">
            Runs at most every {entry.min_interval_minutes} minutes. {entry.terms_note}
          </p>
        )}
        {source.terms_url && (
          <a
            href={source.terms_url}
            target="_blank"
            rel="noopener noreferrer"
            className="w-fit underline"
          >
            Terms and documentation
          </a>
        )}
      </section>
    </div>
  )
}
