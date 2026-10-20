import { Card } from '@/components/Card'
import { PackCard } from '@/features/packs/PackCard'
import { Button } from '@/components/ui/button'
import { describeApiError } from '@/api/errors'
import { useState } from 'react'
import { usePacks, useQueueReextraction, useReextractionPreview } from '@/features/packs/queries'

const WINDOWS = [
  { days: 30, label: '30 days' },
  { days: 90, label: '90 days' },
  { days: 365, label: 'year' },
]

/**
 * Analyse open jobs again with the current prompt. Nothing is re-analysed by itself (it costs
 * local-model time and changes little for most people); this card says how many jobs and how long,
 * and queues them only when the owner confirms.
 */
export function ReextractCard() {
  const [days, setDays] = useState(30)
  const preview = useReextractionPreview(days)
  const queue = useQueueReextraction()
  const queued = queue.isSuccess ? queue.data.queued : null
  return (
    <Card
      title="Analyse open jobs again"
      hint="Jobs analysed before a pack's licences, schedule and travel were asked for keep their old analysis until you do this."
    >
      <label className="flex items-center gap-2 text-sm text-ink-2">
        First seen in the last
        <select
          aria-label="First seen in the last"
          className="rounded-md border border-line-strong bg-surface px-2 py-1 text-sm"
          value={days}
          onChange={(event) => {
            queue.reset()
            setDays(Number(event.target.value))
          }}
        >
          {WINDOWS.map((window) => (
            <option key={window.days} value={window.days}>
              {window.label}
            </option>
          ))}
        </select>
      </label>
      {preview.isPending && <p className="mt-3 text-sm text-ink-3">Counting…</p>}
      {preview.isError && (
        <p role="alert" className="mt-3 text-sm text-bad">
          {describeApiError(preview.error).message}
        </p>
      )}
      {preview.data && preview.data.candidates === 0 && queued === null && (
        <p className="mt-3 text-sm text-ink-2">No open job needs it: they are all up to date.</p>
      )}
      {preview.data && preview.data.candidates > 0 && (
        <div className="mt-3 flex flex-col gap-2 text-sm">
          <p className="text-ink-2">
            {preview.data.candidates} open jobs were analysed with an earlier version of the prompt.
            Analysing them again with {preview.data.model} takes about {preview.data.minutes}{' '}
            minutes while the worker is running. Jobs you ignored or archived are left alone.
          </p>
          <div>
            <Button size="sm" disabled={queue.isPending} onClick={() => queue.mutate(days)}>
              Analyse {preview.data.candidates} jobs again
            </Button>
          </div>
        </div>
      )}
      {queued !== null && (
        <p role="status" className="mt-3 text-sm text-ink-2">
          {queued} jobs queued. The worker analyses them one after another, and their scores are
          updated as each finishes.
        </p>
      )}
      {queue.isError && (
        <p role="alert" className="mt-3 text-sm text-bad">
          {describeApiError(queue.error).message}
        </p>
      )}
    </Card>
  )
}

/**
 * Packs: ready-made vocabularies for fields of work. Each lists the role families and sectors of a
 * field. Switch on the ones you search in; their terms are then offered in your search intent and
 * to the AI that reads job postings. Switching a pack off deletes nothing: saved searches and
 * history keep working.
 */
export function Packs() {
  const { data, isPending, isError, refetch } = usePacks()
  if (isPending) return <p className="px-4 sm:px-6 py-6 text-ink-3">Loading…</p>
  if (isError)
    return (
      <div role="alert" className="flex items-center gap-3 px-4 sm:px-6 py-6 text-bad">
        Could not load the packs.
        <Button variant="outline" size="sm" onClick={() => void refetch()}>
          Try again
        </Button>
      </div>
    )
  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-4 px-4 sm:px-6 py-6">
      <p className="text-sm text-ink-2">
        A pack is a ready-made list of role families and sectors for one field of work. Switch on
        the fields you search in; you can use several at once. Nothing is deleted when you switch a
        pack off: your saved searches and history keep working, and jobs already analysed are not
        analysed again. Prefer to start from scratch? Leave every pack off and add your own terms in
        Vocabulary.
      </p>
      {data.packs.map((pack) => (
        <PackCard key={pack.key} pack={pack} />
      ))}
      <ReextractCard />
    </div>
  )
}
