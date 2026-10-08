import { useState } from 'react'
import { deepEqual } from './deepEqual'

/**
 * An editable copy of saved data. `dirty` is true while the copy differs from `saved`. When
 * `resetKey` changes (a different record or a newer revision arrived) the copy is replaced by
 * the new saved value; this is done while rendering, the pattern React recommends over effects.
 */
export function useDraft<T>(saved: T, resetKey: unknown) {
  const [draft, setDraft] = useState<T>(saved)
  const [key, setKey] = useState(resetKey)
  if (key !== resetKey) {
    setKey(resetKey)
    setDraft(saved)
  }
  return {
    draft,
    setDraft,
    dirty: !deepEqual(draft, saved),
    discard: () => setDraft(saved),
  }
}
