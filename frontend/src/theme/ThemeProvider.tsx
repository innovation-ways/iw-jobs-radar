import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { THEME_STORAGE_KEY, ThemeContext, type ThemeMode } from './theme-context'

function readStoredMode(): ThemeMode {
  // Storage can be blocked (private windows, site settings): fall back to following the system.
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY)
    if (stored === 'light' || stored === 'dark' || stored === 'system') return stored
  } catch {
    /* storage unavailable */
  }
  return 'system'
}

function systemPrefersDark(): boolean {
  return typeof matchMedia === 'function' && matchMedia('(prefers-color-scheme: dark)').matches
}

/** Applies the chosen theme to <html data-theme> and remembers it per browser. */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>(readStoredMode)

  useEffect(() => {
    const resolved = mode === 'system' ? (systemPrefersDark() ? 'dark' : 'light') : mode
    document.documentElement.dataset.theme = resolved
  }, [mode])

  const setMode = useCallback((next: ThemeMode) => {
    setModeState(next)
    try {
      localStorage.setItem(THEME_STORAGE_KEY, next)
    } catch {
      /* storage unavailable: the choice still applies for this session */
    }
  }, [])

  const value = useMemo(() => ({ mode, setMode }), [mode, setMode])
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}
