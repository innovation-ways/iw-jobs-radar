import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import { unwrap } from '@/api/errors'
import type { components } from '@/api/schema'

export type Digest = components['schemas']['DigestRead']

const REFRESH_MS = 60_000

/** The daily digest; refreshed every minute so the sidebar badges follow new runs. */
export function useDigest() {
  return useQuery({
    queryKey: ['digest'],
    queryFn: () => unwrap(api.GET('/api/v1/digests/daily')),
    refetchInterval: REFRESH_MS,
  })
}

/** Counts for the sidebar badges: items to review, new on Today, sources needing attention. */
export function useNavBadges() {
  const digest = useDigest()
  const inbox = useQuery({
    queryKey: ['inbox', 'badge'],
    queryFn: () =>
      unwrap(api.GET('/api/v1/inbox', { params: { query: { state: 'unread', limit: 1 } } })),
    refetchInterval: REFRESH_MS,
  })
  return {
    today:
      (digest.data?.counts?.new_high_fit ?? 0) + (digest.data?.counts?.changed_shortlisted ?? 0),
    inbox: (inbox.data?.counts?.unread ?? 0) + (inbox.data?.counts?.updated_unread ?? 0),
    sources: digest.data?.counts?.sources_needing_attention ?? 0,
  }
}
