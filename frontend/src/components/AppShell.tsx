import { Menu } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Outlet, useLocation } from 'react-router'
import { Sidebar } from '@/components/Sidebar'
import { ThemeToggle } from '@/components/ThemeToggle'
import { titleFor } from '@/navigation'

/** Outlet context: the header element where a page may portal its own buttons. */
export type ShellContext = { headerSlot: HTMLElement | null }

/**
 * Application frame: sidebar, top bar with the page title (the only h1) and the content area.
 * Below the `md` breakpoint the sidebar is a drawer opened from a menu button in the top bar.
 */
export function AppShell() {
  const { pathname } = useLocation()
  const [headerSlot, setHeaderSlot] = useState<HTMLElement | null>(null)
  const [menuOpen, setMenuOpen] = useState(false)

  // Escape closes the drawer (it only has an effect on a narrow screen, where it can be open).
  useEffect(() => {
    if (!menuOpen) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setMenuOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [menuOpen])

  return (
    <div className="flex h-dvh bg-bg text-ink">
      <Sidebar open={menuOpen} onClose={() => setMenuOpen(false)} />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-2 border-b border-line bg-surface px-3 py-2.5 sm:gap-3 sm:px-5">
          <button
            type="button"
            aria-label="Open navigation menu"
            aria-expanded={menuOpen}
            aria-controls="app-sidebar"
            onClick={() => setMenuOpen(true)}
            className="-ml-1 grid size-9 shrink-0 place-items-center rounded-md text-ink-2 hover:bg-surface-2 md:hidden"
          >
            <Menu className="size-5" aria-hidden="true" />
          </button>
          <h1 className="min-w-0 truncate text-[15px] font-semibold tracking-tight">
            {titleFor(pathname)}
          </h1>
          <div className="flex-1" />
          <ThemeToggle />
          {/* Pages portal their own header buttons here (e.g. the Inbox shortcuts help). */}
          <div ref={setHeaderSlot} className="flex items-center" />
        </header>
        <main className="min-h-0 flex-1 overflow-y-auto">
          <Outlet context={{ headerSlot } satisfies ShellContext} />
        </main>
      </div>
    </div>
  )
}
