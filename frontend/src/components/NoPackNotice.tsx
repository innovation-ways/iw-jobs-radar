import { Link } from 'react-router'
import { usePacks } from '@/features/packs/queries'

/**
 * A reminder shown while no domain pack is switched on: without one, role families and sectors
 * are empty apart from the terms the owner added. Renders nothing while loading, on error or once
 * a pack is on, so it never gets in the way.
 */
export function NoPackNotice() {
  const { data } = usePacks()
  if (data?.active_count !== 0) return null
  return (
    <p
      role="status"
      className="border-b border-line bg-surface-2 px-4 sm:px-6 py-2 text-sm text-ink-2"
    >
      No pack is switched on, so there are no role families or sectors to choose from yet. Pick the
      fields you search in on the{' '}
      <Link to="/packs" className="underline">
        Packs
      </Link>{' '}
      screen, or add your own terms in{' '}
      <Link to="/vocabulary" className="underline">
        Vocabulary
      </Link>
      .
    </p>
  )
}
