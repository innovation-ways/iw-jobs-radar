import { useTheme } from '@/theme/useTheme'
import type { ThemeMode } from '@/theme/theme-context'
import { cn } from '@/lib/utils'

const OPTIONS: { mode: ThemeMode; label: string }[] = [
  { mode: 'light', label: 'Light' },
  { mode: 'dark', label: 'Dark' },
  { mode: 'system', label: 'System' },
]

/** Segmented control to choose light, dark or the operating-system theme. */
export function ThemeToggle() {
  const { mode, setMode } = useTheme()
  return (
    <div
      role="group"
      aria-label="Theme"
      className="inline-flex overflow-hidden rounded-md border border-line-strong"
    >
      {OPTIONS.map(({ mode: option, label }, index) => (
        <button
          key={option}
          type="button"
          aria-pressed={mode === option}
          onClick={() => setMode(option)}
          className={cn(
            'px-3 py-1 text-xs text-ink-2 hover:bg-surface-2',
            index > 0 && 'border-l border-line-strong',
            mode === option && 'bg-brand-soft font-semibold text-brand-text',
          )}
        >
          {label}
        </button>
      ))}
    </div>
  )
}
