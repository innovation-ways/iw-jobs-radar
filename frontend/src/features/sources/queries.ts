import { useEffect, useRef } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'
import { unwrap } from '@/api/errors'
import type { components } from '@/api/schema'

export type SourceRead = components['schemas']['SourceRead']
export type CollectionRunRead = components['schemas']['CollectionRunRead']

const SOURCES = ['sources'] as const
const RUNS = ['collection-runs'] as const
const POLL_MS = 1500

/** The run (if any) that is queued or running; the collection is executed in the background. */
export function findActiveRun(
  runs: CollectionRunRead[] | undefined,
): CollectionRunRead | undefined {
  return runs?.find((run) => run.status === 'queued' || run.status === 'running')
}

/**
 * Sources with their status plus recent runs. While a run is in progress both are polled, and
 * the sources are refreshed once more when it ends so the final counts appear.
 */
export function useSourcesData() {
  const queryClient = useQueryClient()
  const runs = useQuery({
    queryKey: RUNS,
    queryFn: async () =>
      (await unwrap(api.GET('/api/v1/collection-runs', { params: { query: { limit: 5 } } }))).items,
    refetchInterval: (query) => (findActiveRun(query.state.data) ? POLL_MS : false),
  })
  const activeRun = findActiveRun(runs.data)
  const sources = useQuery({
    queryKey: SOURCES,
    queryFn: async () => (await unwrap(api.GET('/api/v1/sources'))).items,
    refetchInterval: activeRun ? POLL_MS : false,
  })

  const wasActive = useRef(false)
  useEffect(() => {
    if (wasActive.current && !activeRun) void queryClient.invalidateQueries({ queryKey: SOURCES })
    wasActive.current = Boolean(activeRun)
  }, [activeRun, queryClient])

  return { sources, runs, activeRun }
}

/** Mutations of the Sources screen; each refreshes what it changes. */
export function useSourceActions() {
  const queryClient = useQueryClient()
  const refresh = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: SOURCES }),
      queryClient.invalidateQueries({ queryKey: RUNS }),
    ])

  const addBoard = useMutation({
    mutationFn: (token: string) =>
      unwrap(
        api.POST('/api/v1/sources', {
          body: { source_type: 'greenhouse', external_identifier: token, enabled: true },
        }),
      ),
    onSuccess: refresh,
  })
  const runSource = useMutation({
    mutationFn: (sourceId: number) =>
      unwrap(
        api.POST('/api/v1/sources/{source_configuration_id}/run', {
          params: { path: { source_configuration_id: sourceId } },
        }),
      ),
    onSuccess: refresh,
  })
  const runAll = useMutation({
    mutationFn: () => unwrap(api.POST('/api/v1/collection-runs')),
    onSuccess: refresh,
  })
  const setEnabled = useMutation({
    mutationFn: (source: { id: number; version: number; enabled: boolean }) =>
      unwrap(
        api.PUT('/api/v1/sources/{source_configuration_id}', {
          params: { path: { source_configuration_id: source.id } },
          body: { expected_version: source.version, enabled: source.enabled },
        }),
      ),
    // Refresh even on failure: a version conflict means the list on screen is stale.
    onSettled: refresh,
  })
  return { addBoard, runSource, runAll, setEnabled }
}
