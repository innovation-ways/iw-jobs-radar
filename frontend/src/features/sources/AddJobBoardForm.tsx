import { useId, useState, type FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import { describeApiError } from '@/api/errors'
import { BoardFiltersFields } from './BoardFiltersFields'
import { filtersProblem, withDefaults } from './filters'
import {
  type CatalogueEntryRead,
  type JobBoardFilters,
  type SourcePreviewRead,
  type SourceRead,
  type useJobBoardActions,
} from './queries'

type Actions = ReturnType<typeof useJobBoardActions>

/** The text for a preview: how many of the board's postings pass the filters. */
function previewText(preview: SourcePreviewRead): string {
  const total = preview.postings_total.toLocaleString('en')
  const matching = preview.postings_matching.toLocaleString('en')
  return preview.matching_is_lower_bound
    ? `Found at least ${matching} postings that match your filters (the check stopped early, so the real number is higher).`
    : `${matching} of ${total} postings match your filters.`
}

/**
 * Adds one catalogue board: its key (when it needs one), the filters, a preview of how many
 * postings would be kept, then Add. The preview is tied to the exact values that were checked, so
 * changing a filter or the key requires checking again before Add is possible.
 *
 * @param entry the chosen catalogue board
 * @param located whether the profile and intents give a location to look in
 * @param actions the job board mutations
 * @param onAdded called with the new source after it was saved
 * @param onCancel called to close the form
 */
export function AddJobBoardForm({
  entry,
  located,
  actions,
  onAdded,
  onCancel,
}: {
  entry: CatalogueEntryRead
  located: boolean
  actions: Actions
  onAdded: (source: SourceRead) => void
  onCancel: () => void
}) {
  const keyId = useId()
  const [credential, setCredential] = useState('')
  const [filters, setFilters] = useState<JobBoardFilters>(withDefaults(entry.default_filters))
  const [checked, setChecked] = useState<{ signature: string; preview: SourcePreviewRead } | null>(
    null,
  )
  const signature = JSON.stringify([credential.trim(), filters])
  const preview = checked?.signature === signature ? checked.preview : null
  const needsKey = entry.requires_credential && !credential.trim()
  const problem = filtersProblem(filters)
  const draft = { catalogueKey: entry.catalogue_key, credential, filters }
  const error = actions.previewBoard.isError
    ? actions.previewBoard.error
    : actions.addJobBoard.isError
      ? actions.addJobBoard.error
      : null

  function check() {
    actions.previewBoard.mutate(draft, {
      onSuccess: (result) => setChecked({ signature, preview: result }),
    })
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!preview || actions.addJobBoard.isPending) return
    actions.addJobBoard.mutate(draft, { onSuccess: onAdded })
  }

  return (
    <form
      onSubmit={submit}
      aria-label={`Add ${entry.display_name}`}
      className="flex flex-col gap-4 rounded-md border border-line bg-surface-2 p-4"
    >
      <h3 className="text-sm font-semibold">Add {entry.display_name}</h3>
      {entry.requires_credential && (
        <div className="flex max-w-sm flex-col gap-1">
          <label htmlFor={keyId} className="text-xs text-ink-2">
            {entry.credential_label ?? 'API key'}
          </label>
          <input
            id={keyId}
            type="password"
            autoComplete="off"
            aria-describedby={`${keyId}-hint`}
            value={credential}
            onChange={(event) => setCredential(event.target.value)}
            className="rounded-md border border-line-strong bg-surface px-2.5 py-1.5 text-sm text-ink"
          />
          <span id={`${keyId}-hint`} className="text-xs text-ink-3">
            Stored encrypted. It is sent for the check and never shown again.
          </span>
        </div>
      )}
      <BoardFiltersFields
        value={filters}
        categories={entry.available_categories}
        onChange={setFilters}
        idPrefix={`add-${entry.catalogue_key}`}
      />
      <p className="text-xs text-ink-3">
        {entry.terms_note}{' '}
        <a href={entry.terms_url} target="_blank" rel="noopener noreferrer" className="underline">
          Terms
        </a>{' '}
        (read on {entry.terms_read_on}).
      </p>
      {!located && (
        <p role="status" className="text-sm text-caution">
          Set your location in Profile & intent to check this board.
        </p>
      )}
      <div className="flex flex-wrap items-center gap-3">
        <Button
          type="button"
          variant="outline"
          disabled={!located || needsKey || problem !== null || actions.previewBoard.isPending}
          onClick={check}
        >
          {actions.previewBoard.isPending ? 'Checking…' : 'Check & preview'}
        </Button>
        <Button type="submit" disabled={!preview || actions.addJobBoard.isPending}>
          Add {entry.display_name} to my sources
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
      </div>
      {preview && (
        <p role="status" className="text-sm text-good">
          {previewText(preview)}
        </p>
      )}
      {error && (
        <p role="alert" className="text-sm text-bad">
          {describeApiError(error).message}
        </p>
      )}
    </form>
  )
}
