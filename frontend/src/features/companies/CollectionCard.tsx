import { useState } from 'react'
import { Button } from '@/components/ui/button'
import type { components } from '@/api/schema'
import { FollowCompanyDialog } from './FollowCompanyDialog'
import { sourceLabel, useSourceReader, useTurnOffFilters } from './onboarding'

type Board = components['schemas']['BoardRead']

const RESULT_WORDS: Record<string, string> = {
  success: 'succeeded',
  not_modified: 'unchanged',
  partial: 'partial: limit reached',
  skipped: 'skipped: ran recently',
  failed: 'failed',
}

/** The owner's words for a failure class of a careers-page source. */
function failureNote(errorClass: string | null | undefined): string | null {
  if (errorClass === 'schema_changed') {
    return 'The page no longer matches the approved reader. Propose a new one below.'
  }
  if (errorClass === 'configuration')
    return 'The site does not allow reading this page (robots.txt).'
  return errorClass ? `Reason: ${errorClass.replace(/_/g, ' ')}` : null
}

/** Propose and approve a new reader for a careers-page source whose page changed. */
function ReaderRepair({ board }: { board: Board }) {
  const { propose, approve } = useSourceReader(board.source_configuration_id)
  const proposal = propose.data
  return (
    <div className="mt-2 flex flex-col gap-2 rounded-md bg-surface-2 p-2.5 text-sm">
      {!proposal && (
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={propose.isPending}
            onClick={() => propose.mutate()}
          >
            {propose.isPending ? 'Asking the local model…' : 'Propose a new reader'}
          </Button>
          <span className="text-xs text-ink-3">
            The local model suggests it; you review it first.
          </span>
        </div>
      )}
      {proposal && (
        <>
          <p className="font-medium">The new reader finds {proposal.preview.length} postings:</p>
          <ul className="text-xs text-ink-2">
            {proposal.preview.map((posting) => (
              <li key={posting.url}>{posting.title}</li>
            ))}
          </ul>
          <div className="flex gap-2">
            <Button
              size="sm"
              disabled={approve.isPending || approve.isSuccess}
              onClick={() => approve.mutate({ proposal, version: board.version })}
            >
              {approve.isSuccess ? 'Approved' : 'Approve the new reader'}
            </Button>
            <Button variant="ghost" size="sm" onClick={() => propose.reset()}>
              Discard
            </Button>
          </div>
        </>
      )}
      {(propose.isError || approve.isError) && (
        <p role="alert" className="text-xs text-bad">
          {propose.error?.message ?? approve.error?.message}
        </p>
      )}
    </div>
  )
}

/** What the owner's filters left out of the last run, with a way to turn them off and collect. */
function FilterNote({ board }: { board: Board }) {
  const turnOff = useTurnOffFilters(board.source_configuration_id)
  const dropped = board.last_dropped_count ?? 0
  if (!board.filters_enabled || dropped === 0) return null
  return (
    <div className="mt-1 flex flex-wrap items-center gap-2 text-xs">
      <span className="text-ink-2">{dropped} left out by your filters.</span>
      <Button
        variant="outline"
        size="sm"
        disabled={turnOff.isPending || turnOff.isSuccess}
        onClick={() => turnOff.mutate(board.version)}
      >
        {turnOff.isSuccess ? 'Collecting…' : 'Turn off filters and collect'}
      </Button>
      {turnOff.isError && (
        <span role="alert" className="text-bad">
          {turnOff.error.message}
        </span>
      )}
    </div>
  )
}

/**
 * How the company's offers are collected (ADR-070): each source with its latest result, a message
 * for a company that is followed by hand only, the careers address, and "Detect again", which
 * reopens the follow dialog with the company's name and addresses filled in.
 */
export function CollectionCard({
  name,
  websiteUrl,
  careersUrl,
  boards,
}: {
  name: string
  websiteUrl: string | null
  careersUrl: string | null
  boards: Board[]
}) {
  const [detecting, setDetecting] = useState(false)
  const careers = careersUrl ?? ''
  const hasSource = boards.some((b) => b.enabled)
  return (
    <section aria-labelledby="collection" className="rounded-lg border border-line bg-surface p-4">
      <div className="mb-2 flex items-center gap-2">
        <h3 id="collection" className="flex-1 text-sm font-semibold">
          Collection
        </h3>
        <span
          className={`rounded-full px-2 text-xs font-medium ${hasSource ? 'bg-good-bg text-good' : 'bg-caution-bg text-caution'}`}
        >
          {hasSource ? 'Collecting' : 'Not collected'}
        </span>
      </div>
      {boards.length === 0 && (
        <p className="text-sm text-ink-2">
          No source collects this company’s offers automatically.
          {careers && ' Its careers page is linked below.'}
        </p>
      )}
      <ul className="flex flex-col gap-3">
        {boards.map((board) => {
          const note = board.last_outcome === 'failed' ? failureNote(board.last_error_class) : null
          return (
            <li key={board.source_configuration_id} className="text-sm">
              <div className="font-medium">
                {sourceLabel(board.source_type)}
                {!board.enabled && <span className="ml-2 text-xs text-ink-3">(disabled)</span>}
              </div>
              <div className="text-xs text-ink-2 tabular-nums">
                {board.last_outcome
                  ? `Last run ${RESULT_WORDS[board.last_outcome] ?? board.last_outcome}${board.last_collected_count !== null && board.last_collected_count !== undefined ? ` · ${board.last_collected_count} postings` : ''}`
                  : 'Not run yet'}
              </div>
              <FilterNote board={board} />
              {note && <p className="text-xs text-bad">{note}</p>}
              {board.source_type === 'page_config' &&
                board.last_error_class === 'schema_changed' && <ReaderRepair board={board} />}
            </li>
          )
        })}
      </ul>
      <div className="mt-3 flex flex-wrap items-center gap-3 text-sm">
        {careers && (
          <a
            href={careers}
            target="_blank"
            rel="noreferrer noopener"
            className="text-brand-text underline"
          >
            Careers page
          </a>
        )}
        {websiteUrl && (
          <Button variant="outline" size="sm" onClick={() => setDetecting(true)}>
            Detect again
          </Button>
        )}
      </div>
      {detecting && (
        <FollowCompanyDialog
          initial={{ name, websiteUrl: websiteUrl ?? '', careersUrl: careers }}
          onClose={() => setDetecting(false)}
          onDone={() => setDetecting(false)}
        />
      )}
    </section>
  )
}
