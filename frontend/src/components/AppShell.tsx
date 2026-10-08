import { Outlet, useLocation } from 'react-router'
import { Sidebar } from '@/components/Sidebar'
import { ThemeToggle } from '@/components/ThemeToggle'
import { titleFor } from '@/navigation'

/** Application frame: sidebar, top bar with the page title (the only h1) and the content area. */
export function AppShell() {
  const { pathname } = useLocation()
  return (
    <div className="flex h-screen bg-bg text-ink">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-3 border-b border-line bg-surface px-5 py-2.5">
          <h1 className="text-[15px] font-semibold tracking-tight">{titleFor(pathname)}</h1>
          <div className="flex-1" />
          <ThemeToggle />
        </header>
        <main className="min-h-0 flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
