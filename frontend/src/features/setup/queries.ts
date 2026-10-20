import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import { unwrap } from '@/api/errors'

/** Whether the installation still has to be set up (no profile and no pack switched on). */
export function useSetupStatus() {
  return useQuery({
    queryKey: ['setup-status'],
    retry: false,
    queryFn: () => unwrap(api.GET('/api/v1/setup/status')),
  })
}

/** What a first search intent starts with: the suggestions of the first pack switched on. */
export function useIntentDefaults() {
  return useQuery({
    queryKey: ['intent-defaults'],
    queryFn: () => unwrap(api.GET('/api/v1/setup/intent-defaults')),
  })
}

/** The key under which the owner's choice to skip the setup is remembered in this browser. */
export const SETUP_SKIPPED_KEY = 'jobs-radar-setup-skipped'

/** Whether the owner chose to skip the setup; storage that cannot be read counts as "no". */
export function setupSkipped(): boolean {
  try {
    return window.localStorage.getItem(SETUP_SKIPPED_KEY) === '1'
  } catch {
    return false
  }
}

/** Remember that the owner skipped the setup (best effort: private windows may refuse). */
export function skipSetup(): void {
  try {
    window.localStorage.setItem(SETUP_SKIPPED_KEY, '1')
  } catch {
    // Without storage the setup is simply offered again next time.
  }
}
