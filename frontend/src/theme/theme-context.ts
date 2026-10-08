import { createContext } from 'react'

export type ThemeMode = 'light' | 'dark' | 'system'

export interface ThemeContextValue {
  /** The user's choice. */
  mode: ThemeMode
  /** Change the choice; it is persisted when browser storage is available. */
  setMode: (mode: ThemeMode) => void
}

export const ThemeContext = createContext<ThemeContextValue | null>(null)
export const THEME_STORAGE_KEY = 'jobs-radar.theme'
