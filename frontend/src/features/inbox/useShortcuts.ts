import { useEffect } from 'react'

export type Shortcuts = Record<string, () => void>

/**
 * Single-key shortcuts for the inbox. Keys typed into a field, and combinations with Ctrl, Alt or
 * Meta, are left alone so ordinary typing and browser shortcuts keep working.
 */
export function useShortcuts(shortcuts: Shortcuts, enabled = true): void {
  useEffect(() => {
    if (!enabled) return
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null
      if (target && /^(input|select|textarea)$/i.test(target.tagName)) return
      if (event.ctrlKey || event.altKey || event.metaKey) return
      const handler = shortcuts[event.key]
      if (!handler) return
      event.preventDefault()
      handler()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [shortcuts, enabled])
}
