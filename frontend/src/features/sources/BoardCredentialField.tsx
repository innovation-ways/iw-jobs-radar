import { useState } from 'react'
import { Button } from '@/components/ui/button'

/**
 * A write-only key field for a job board that needs one: the key is sent once and never shown
 * again, so a saved key appears only as a replace prompt.
 *
 * @param label the board's name for its key, for example "ITJobs API key"
 * @param saved whether a key is stored
 * @param updatedAt when the stored key was written, if any
 * @param busy true while a change is being saved
 * @param onSave called with the new key; the field is cleared afterwards
 * @param onRemove called to delete the stored key
 */
export function BoardCredentialField({
  label,
  saved,
  updatedAt,
  busy,
  onSave,
  onRemove,
}: {
  label: string
  saved: boolean
  updatedAt: string | null
  busy: boolean
  onSave: (secret: string, done: () => void) => void
  onRemove: () => void
}) {
  const [secret, setSecret] = useState('')
  return (
    <div className="flex flex-col gap-1.5">
      <p className="text-sm">
        Key: {saved ? 'saved' : 'not set'}
        {saved && updatedAt && (
          <span className="text-ink-3"> (updated {new Date(updatedAt).toLocaleDateString()})</span>
        )}
      </p>
      <div className="flex flex-wrap items-end gap-2.5">
        <label className="flex flex-col gap-1 text-xs text-ink-2">
          {label}
          <input
            type="password"
            autoComplete="off"
            value={secret}
            placeholder={saved ? '•••••• (replace)' : ''}
            onChange={(event) => setSecret(event.target.value)}
            className="min-w-52 rounded-md border border-line-strong bg-surface px-2.5 py-1.5 text-sm text-ink"
          />
        </label>
        <Button
          type="button"
          size="sm"
          disabled={!secret.trim() || busy}
          onClick={() => onSave(secret.trim(), () => setSecret(''))}
        >
          {saved ? 'Replace key' : 'Save key'}
        </Button>
        {saved && (
          <Button type="button" size="sm" variant="ghost" disabled={busy} onClick={onRemove}>
            Remove key
          </Button>
        )}
      </div>
      <p className="text-xs text-ink-3">
        The key is checked with the board, stored encrypted and never shown again. Removing it also
        switches the board off.
      </p>
    </div>
  )
}
