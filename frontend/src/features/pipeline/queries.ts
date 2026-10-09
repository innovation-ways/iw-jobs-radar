import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import { unwrap } from '@/api/errors'

/** Refresh quickly while the details are open, slowly for the one-line summary. */
const OPEN_REFRESH_MS = 5_000
const CLOSED_REFRESH_MS = 30_000

/** How far analysis and scoring have got, polled so the owner can watch the worker. */
export function usePipelineStatus(detailsOpen: boolean) {
  return useQuery({
    queryKey: ['pipeline', 'status'],
    queryFn: () => unwrap(api.GET('/api/v1/pipeline/status')),
    refetchInterval: detailsOpen ? OPEN_REFRESH_MS : CLOSED_REFRESH_MS,
  })
}
