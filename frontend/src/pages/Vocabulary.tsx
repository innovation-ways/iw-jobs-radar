import { useState, type FormEvent } from 'react'
import { Card } from '@/components/Card'
import { Button } from '@/components/ui/button'
import { describeApiError } from '@/api/errors'
import {
  useVocabularyActions,
  useVocabularyTerms,
  type VocabularyTerm,
} from '@/features/vocabulary/queries'

const field = 'rounded-md border border-line-strong bg-surface px-2.5 py-1.5 text-sm'

const KINDS = [
  { kind: 'role_family', title: 'Role families', singular: 'role family' },
  { kind: 'sector', title: 'Sectors', singular: 'sector' },
] as const

/** One term: its label, where it came from, whether it is offered, and a way to rename it. */
function TermRow({ term }: { term: VocabularyTerm }) {
  const { changeTerm } = useVocabularyActions()
  const [editing, setEditing] = useState(false)
  const [label, setLabel] = useState(term.label)

  const save = (event: FormEvent) => {
    event.preventDefault()
    changeTerm.mutate(
      { kind: term.kind, termKey: term.term_key, label },
      { onSuccess: () => setEditing(false) },
    )
  }

  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-1 py-1.5">
      {editing ? (
        <form onSubmit={save} className="flex flex-wrap items-center gap-2">
          <input
            aria-label={`Label of ${term.label}`}
            className={field}
            value={label}
            maxLength={120}
            onChange={(event) => setLabel(event.target.value)}
          />
          <Button type="submit" size="sm" disabled={changeTerm.isPending || !label.trim()}>
            Save
          </Button>
          <Button type="button" size="sm" variant="outline" onClick={() => setEditing(false)}>
            Cancel
          </Button>
        </form>
      ) : (
        <>
          <span className={term.active ? 'text-sm' : 'text-sm text-ink-3'}>{term.label}</span>
          <span className="rounded-full border border-line px-2 py-0.5 text-xs text-ink-2">
            {term.origin === 'user' ? 'Added by you' : 'Built in'}
          </span>
          {!term.active && <span className="text-xs font-medium text-ink-2">Switched off</span>}
          <span className="ml-auto flex items-center gap-3">
            <label className="flex items-center gap-1.5 text-xs text-ink-2">
              <input
                type="checkbox"
                checked={term.active}
                disabled={changeTerm.isPending}
                aria-label={`Offer ${term.label}`}
                onChange={() =>
                  changeTerm.mutate({
                    kind: term.kind,
                    termKey: term.term_key,
                    active: !term.active,
                  })
                }
              />
              Offered
            </label>
            <Button
              type="button"
              size="sm"
              variant="outline"
              aria-label={`Rename ${term.label}`}
              onClick={() => {
                setLabel(term.label)
                setEditing(true)
              }}
            >
              Rename
            </Button>
          </span>
        </>
      )}
      {changeTerm.isError && (
        <p role="alert" className="w-full text-xs text-bad">
          {describeApiError(changeTerm.error).message}
        </p>
      )}
    </li>
  )
}

/** The list of one vocabulary with the form that adds a term to it. */
function VocabularyCard({
  kind,
  title,
  singular,
  terms,
}: {
  kind: string
  title: string
  singular: string
  terms: VocabularyTerm[]
}) {
  const { addTerm } = useVocabularyActions()
  const [label, setLabel] = useState('')

  const add = (event: FormEvent) => {
    event.preventDefault()
    addTerm.mutate({ kind, label }, { onSuccess: () => setLabel('') })
  }

  return (
    <Card title={title}>
      <ul className="divide-y divide-line">
        {terms.map((term) => (
          <TermRow key={term.term_key} term={term} />
        ))}
      </ul>
      <form onSubmit={add} className="mt-3 flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1 text-xs text-ink-2">
          {`New ${singular}`}
          <input
            className={field}
            value={label}
            maxLength={120}
            onChange={(event) => setLabel(event.target.value)}
          />
        </label>
        <Button type="submit" size="sm" disabled={addTerm.isPending || !label.trim()}>
          Add
        </Button>
      </form>
      {addTerm.isError && (
        <p role="alert" className="mt-2 text-sm text-bad">
          {describeApiError(addTerm.error).message}
        </p>
      )}
    </Card>
  )
}

/**
 * Vocabulary: the role families and sectors that jobs are classified into and that the search
 * intent takes a stance on. Built-in terms can be renamed and switched off; terms added here join
 * the next job analyses. Nothing is deleted, and a term's key never changes.
 */
export function Vocabulary() {
  const { data, isPending, isError, refetch } = useVocabularyTerms()
  if (isPending) return <p className="px-4 sm:px-6 py-6 text-ink-3">Loading…</p>
  if (isError)
    return (
      <div role="alert" className="flex items-center gap-3 px-4 sm:px-6 py-6 text-bad">
        Could not load the vocabulary.
        <Button variant="outline" size="sm" onClick={() => void refetch()}>
          Try again
        </Button>
      </div>
    )
  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-4 px-4 sm:px-6 py-6">
      <p className="text-sm text-ink-2">
        Jobs are sorted into these role families and sectors, and your search intent takes a stance
        on each. Switched-off terms stay in saved searches and history but are not offered for new
        choices or to the AI that reads job postings. Jobs already analysed are not analysed again
        when you change this list.
      </p>
      {KINDS.map(({ kind, title, singular }) => (
        <VocabularyCard
          key={kind}
          kind={kind}
          title={title}
          singular={singular}
          terms={data.terms.filter((term) => term.kind === kind)}
        />
      ))}
    </div>
  )
}
