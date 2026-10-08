import { useEffect } from 'react'

const SHORTCUTS: [keys: string, text: string][] = [
  ['j  k', 'Next / previous job'],
  ['s', 'Shortlist / remove from shortlist'],
  ['u', 'Mark unread'],
  ['r', 'Restore (ignored, archived, applied)'],
  ['z', 'Undo last action'],
  ['x', 'Ignore'],
  ['e', 'Archive'],
  ['a', 'Record application'],
  ['/', 'Search'],
  ['Esc', 'Close this panel'],
]

/** The keyboard shortcuts of the inbox, shown in a dialog that Escape or a click outside closes. */
export function ShortcutsHelp({ onClose }: { onClose: () => void }) {
  useEffect(() => {
    const close = (event: KeyboardEvent) => event.key === 'Escape' && onClose()
    window.addEventListener('keydown', close)
    return () => window.removeEventListener('keydown', close)
  }, [onClose])
  return (
    <div
      className="fixed inset-0 z-30 grid place-items-center bg-black/40"
      onClick={(event) => event.target === event.currentTarget && onClose()}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Keyboard shortcuts"
        className="w-[360px] rounded-xl border border-line bg-surface p-5 shadow-lg"
      >
        <h3 className="mb-2.5 text-[15px] font-semibold">Keyboard shortcuts</h3>
        <table className="w-full text-sm">
          <tbody>
            {SHORTCUTS.map(([keys, text]) => (
              <tr key={keys}>
                <td className="py-1 pr-4 whitespace-nowrap">
                  {keys.split('  ').map((key) => (
                    <kbd
                      key={key}
                      className="mr-1 rounded border border-line-strong border-b-2 bg-surface px-1.5 py-px text-[11px] text-ink-2"
                    >
                      {key}
                    </kbd>
                  ))}
                </td>
                <td className="text-ink-2">{text}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
