import { Navigate } from 'react-router'
import { setupSkipped, useSetupStatus } from '@/features/setup/queries'

/**
 * The page at the root address: the first-run setup for an installation that has no profile and no
 * pack yet, the inbox for everyone else. It never traps the owner: skipping the setup is
 * remembered, and if the status cannot be read the inbox opens.
 */
export function Home() {
  const status = useSetupStatus()
  if (status.isPending) return <p className="px-4 sm:px-6 py-6 text-ink-3">Loading…</p>
  const needsSetup = status.data?.needs_setup === true && !setupSkipped()
  return <Navigate to={needsSetup ? '/setup' : '/inbox'} replace />
}
