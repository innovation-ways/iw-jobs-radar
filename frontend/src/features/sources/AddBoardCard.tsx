import { useState, type FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import { useSourceActions } from './queries'

/**
 * Adds a Greenhouse board by token. The API checks the token against the real board before saving,
 * so a typo is reported here instead of becoming a broken source.
 */
export function AddBoardCard({
  addBoard,
}: {
  addBoard: ReturnType<typeof useSourceActions>['addBoard']
}) {
  const [token, setToken] = useState('')
  const trimmed = token.trim()

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!trimmed || addBoard.isPending) return
    addBoard.mutate(trimmed, { onSuccess: () => setToken('') })
  }

  return (
    <section aria-labelledby="add-board" className="rounded-lg border border-line bg-surface p-4">
      <h2 id="add-board" className="text-sm font-semibold">
        Add a board
      </h2>
      <form onSubmit={submit} className="mt-3 flex flex-wrap items-end gap-2.5">
        <label className="flex flex-col gap-1 text-xs text-ink-2">
          Board token
          <input
            value={token}
            onChange={(event) => setToken(event.target.value)}
            aria-describedby="board-hint"
            autoComplete="off"
            spellCheck={false}
            className="min-w-52 rounded-md border border-line-strong bg-surface px-2.5 py-1.5 text-sm text-ink"
          />
        </label>
        <Button type="submit" disabled={!trimmed || addBoard.isPending}>
          {addBoard.isPending ? 'Validating…' : 'Validate & add'}
        </Button>
      </form>
      <p id="board-hint" className="mt-2.5 text-xs text-ink-3">
        The token is the last part of a company&apos;s Greenhouse board address. It is checked
        before it is saved.
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
