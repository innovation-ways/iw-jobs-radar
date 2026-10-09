import { useState, type FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import { useSourceActions, type CompanyBoardType } from './queries'

interface BoardKind {
  label: string
  idLabel: string
  hint: string
  /** Whether the ATS publishes no company name, so the owner may type it. */
  asksName: boolean
}

const KINDS: Record<CompanyBoardType, BoardKind> = {
  greenhouse: {
    label: 'Greenhouse',
    idLabel: 'Board token',
    hint: "The token is the last part of a company's Greenhouse board address.",
    asksName: false,
  },
  lever: {
    label: 'Lever',
    idLabel: 'Company identifier',
    hint: 'The identifier is the last part of the address jobs.lever.co/<identifier>.',
    asksName: true,
  },
  ashby: {
    label: 'Ashby',
    idLabel: 'Company identifier',
    hint: 'The identifier is the last part of the address jobs.ashbyhq.com/<identifier>.',
    asksName: true,
  },
  smartrecruiters: {
    label: 'SmartRecruiters',
    idLabel: 'Company identifier',
    hint: 'The identifier is the last part of the address jobs.smartrecruiters.com/<identifier>.',
    asksName: false,
  },
}

/**
 * Adds a company board by its identifier on one of the supported applicant tracking systems. The
 * API checks the identifier against the real board before saving, so a typo is reported here
 * instead of becoming a broken source. Lever and Ashby publish no company name, so the owner can
 * type it; otherwise a name is guessed from the identifier.
 */
export function AddBoardCard({
  addBoard,
}: {
  addBoard: ReturnType<typeof useSourceActions>['addBoard']
}) {
  const [kind, setKind] = useState<CompanyBoardType>('greenhouse')
  const [token, setToken] = useState('')
  const [name, setName] = useState('')
  const trimmed = token.trim()
  const info = KINDS[kind]

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!trimmed || addBoard.isPending) return
    const displayName = info.asksName ? name.trim() : ''
    addBoard.mutate(
      { sourceType: kind, identifier: trimmed, ...(displayName ? { displayName } : {}) },
      {
        onSuccess: () => {
          setToken('')
          setName('')
        },
      },
    )
  }

  return (
    <section aria-labelledby="add-board" className="rounded-lg border border-line bg-surface p-4">
      <h2 id="add-board" className="text-sm font-semibold">
        Add a board
      </h2>
      <form onSubmit={submit} className="mt-3 flex flex-wrap items-end gap-2.5">
        <label className="flex flex-col gap-1 text-xs text-ink-2">
          Board type
          <select
            value={kind}
            onChange={(event) => setKind(event.target.value as CompanyBoardType)}
            className="rounded-md border border-line-strong bg-surface px-2.5 py-1.5 text-sm text-ink"
          >
            {Object.entries(KINDS).map(([value, item]) => (
              <option key={value} value={value}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-ink-2">
          {info.idLabel}
          <input
            value={token}
            onChange={(event) => setToken(event.target.value)}
            aria-describedby="board-hint"
            autoComplete="off"
            spellCheck={false}
            className="min-w-52 rounded-md border border-line-strong bg-surface px-2.5 py-1.5 text-sm text-ink"
          />
        </label>
        {info.asksName && (
          <label className="flex flex-col gap-1 text-xs text-ink-2">
            Company name (optional)
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              autoComplete="off"
              className="min-w-52 rounded-md border border-line-strong bg-surface px-2.5 py-1.5 text-sm text-ink"
            />
          </label>
        )}
        <Button type="submit" disabled={!trimmed || addBoard.isPending}>
          {addBoard.isPending ? 'Validating…' : 'Validate & add'}
        </Button>
      </form>
      <p id="board-hint" className="mt-2.5 text-xs text-ink-3">
        {info.hint} It is checked before it is saved.
        {info.asksName && ' This board does not publish the company name; type it if you know it.'}
      </p>
      {addBoard.isError && (
        <p role="alert" className="mt-2 text-sm text-bad">
          {addBoard.error.message}
        </p>
      )}
      {addBoard.isSuccess && (
        <p role="status" className="mt-2 text-sm text-good">
          Added {addBoard.data.display_name}. Run it to collect its jobs.
        </p>
      )}
    </section>
  )
}
