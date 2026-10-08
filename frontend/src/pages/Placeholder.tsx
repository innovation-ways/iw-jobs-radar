import { ALL_NAV } from '@/navigation'

/** Stand-in for a screen that a later task implements; shows what the screen will do. */
export function Placeholder({ path }: { path: string }) {
  const item = ALL_NAV.find((entry) => entry.path === path)
  return (
    <div className="mx-auto max-w-3xl px-6 py-8">
      <div className="rounded-lg border border-line bg-surface p-5">
        <h2 className="text-sm font-semibold">Coming soon</h2>
        <p className="mt-1 text-ink-2">{item?.description}</p>
      </div>
    </div>
  )
}
