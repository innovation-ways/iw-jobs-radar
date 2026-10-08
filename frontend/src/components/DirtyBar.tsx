import { useState } from 'react'
import { Button } from '@/components/ui/button'

interface Props {
  dirty: boolean
  saving: boolean
  /** Why the draft cannot be saved yet (shown, and Save is disabled). */
  problem?: string | null
  /** The last save error, if any. */
  error?: string | null
  onSave: (changeNote: string) => void
  onDiscard: () => void
}

/**
 * Sticky bar shown while a draft differs from the saved revision: Save creates a new immutable
 * revision, Discard drops the changes. An optional change note is stored with the revision.
 */
export function DirtyBar({ dirty, saving, problem, error, onSave, onDiscard }: Props) {
  const [note, setNote] = useState('')
  if (!dirty) return null
  return (
    <section
      aria-label="Unsaved changes"
      className="sticky bottom-0 z-10 flex flex-wrap items-center gap-3 border-t border-line bg-surface px-5 py-3 shadow-[0_-4px_16px_rgb(0_0_0/6%)]"
    >
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">
          You have unsaved changes. Saving creates a new revision.
        </p>
        {problem && <p className="text-xs text-caution">{problem}</p>}
        {error && (
          <p role="alert" className="text-xs text-bad">
            {error}
          </p>
        )}
      </div>
      <label className="flex items-center gap-2 text-xs text-ink-2">
        Change note (optional)
        <input
          value={note}
          onChange={(event) => setNote(event.target.value)}
          maxLength={300}
          className="w-56 rounded-md border border-line-strong bg-surface px-2 py-1 text-sm text-ink"
        />
      </label>
      <Button variant="outline" size="sm" onClick={onDiscard} disabled={saving}>
        Discard
      </Button>
      <Button size="sm" disabled={saving || Boolean(problem)} onClick={() => onSave(note.trim())}>
        {saving ? 'Saving…' : 'Save revision'}
      </Button>
    </section>
  )
}
