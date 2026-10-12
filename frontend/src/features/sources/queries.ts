import { useEffect, useRef } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'
import { unwrap } from '@/api/errors'
import type { components } from '@/api/schema'

export type SourceRead = components['schemas']['SourceRead']
export type CatalogueEntryRead = components['schemas']['CatalogueEntryRead']
export type SourcePreviewRead = components['schemas']['SourcePreviewRead']
export type SourceScopeRead = components['schemas']['SourceScopeRead']
/** The API marks fields with defaults as optional, but it always sends all of them. */
export type JobBoardFilters = Required<components['schemas']['JobBoardFilters']>
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

/** The company boards (one company per source) an owner can add by identifier. */
export type CompanyBoardType = 'greenhouse' | 'lever' | 'ashby' | 'smartrecruiters' | 'eightfold'

/** What the owner types to add a company board. */
export interface CompanyBoardDraft {
  sourceType: CompanyBoardType
  identifier: string
  /** Only for boards whose ATS publishes no company name (Lever, Ashby). */
  displayName?: string
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
    mutationFn: (board: CompanyBoardDraft) =>
      unwrap(
        api.POST('/api/v1/sources', {
          body: {
            source_type: board.sourceType,
            external_identifier: board.identifier,
            enabled: true,
            ...(board.displayName ? { display_name: board.displayName } : {}),
          },
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

const CATALOGUE = ['source-catalogue'] as const
const SCOPE = ['source-scope'] as const

/** The job boards that can be added, marking those already configured. */
export function useCatalogue() {
  return useQuery({
    queryKey: CATALOGUE,
    queryFn: async () => (await unwrap(api.GET('/api/v1/source-catalogue'))).items,
  })
}

/** Where job boards look for postings, derived from the profile and the enabled intents. */
export function useSourceScope() {
  return useQuery({
    queryKey: SCOPE,
    queryFn: () => unwrap(api.GET('/api/v1/source-scope')),
  })
}

/** What the owner enters to preview or add a catalogue board. */
export interface BoardDraft {
  catalogueKey: string
  credential?: string
  filters: JobBoardFilters
}

/** Mutations of the Job boards section; each refreshes what it changes. */
export function useJobBoardActions() {
  const queryClient = useQueryClient()
  const refresh = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: SOURCES }),
      queryClient.invalidateQueries({ queryKey: CATALOGUE }),
    ])
  const credentialOf = (draft: BoardDraft) =>
    draft.credential?.trim() ? { credential: draft.credential.trim() } : {}

  const previewBoard = useMutation({
    mutationFn: (draft: BoardDraft) =>
      unwrap(
        api.POST('/api/v1/sources/preview', {
          body: {
            catalogue_key: draft.catalogueKey,
            filters: draft.filters,
            ...credentialOf(draft),
          },
        }),
      ),
  })
  const addJobBoard = useMutation({
    mutationFn: (draft: BoardDraft) =>
      unwrap(
        api.POST('/api/v1/sources', {
          // For a catalogue board the type and the identifier are both the catalogue key.
          body: {
            source_type: draft.catalogueKey as SourceRead['source_type'],
            external_identifier: draft.catalogueKey,
            enabled: true,
            filters: draft.filters,
            ...credentialOf(draft),
          },
        }),
      ),
    onSuccess: refresh,
  })
  const saveFilters = useMutation({
    mutationFn: (change: { id: number; version: number; filters: JobBoardFilters }) =>
      unwrap(
        api.PUT('/api/v1/sources/{source_configuration_id}', {
          params: { path: { source_configuration_id: change.id } },
          body: { expected_version: change.version, filters: change.filters },
        }),
      ),
    // Refresh even on failure: a version conflict means the list on screen is stale.
    onSettled: refresh,
  })
  const clearFilters = useMutation({
    mutationFn: (change: { id: number; version: number }) =>
      unwrap(
        api.PUT('/api/v1/sources/{source_configuration_id}', {
          params: { path: { source_configuration_id: change.id } },
          body: { expected_version: change.version, clear_filters: true },
        }),
      ),
    onSettled: refresh,
  })
  const writeKey = useMutation({
    mutationFn: (change: { id: number; secret: string }) =>
      unwrap(
        api.PUT('/api/v1/sources/{source_configuration_id}/credential', {
          params: { path: { source_configuration_id: change.id } },
          body: { secret: change.secret },
        }),
      ),
    onSettled: refresh,
  })
  const removeKey = useMutation({
    mutationFn: (id: number) =>
      unwrap(
        api.DELETE('/api/v1/sources/{source_configuration_id}/credential', {
          params: { path: { source_configuration_id: id } },
        }),
      ),
    onSettled: refresh,
  })
  return { previewBoard, addJobBoard, saveFilters, clearFilters, writeKey, removeKey }
}

export type ScheduleRead = components['schemas']['ScheduleRead']
const SCHEDULE = ['schedule'] as const

/** The daily schedule (run times, time zone, on/off and the next run). */
export function useSchedule() {
  return useQuery({
    queryKey: SCHEDULE,
    queryFn: () => unwrap(api.GET('/api/v1/settings/schedule')),
  })
}

/** Save the schedule with the version the owner saw; the worker picks it up on its next poll. */
export function useSaveSchedule() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (change: {
      run_times_local: string[]
      timezone: string
      enabled: boolean
      company_recency_days: number
      set_aside_below_fit: number
      expected_version: number
    }) => unwrap(api.PUT('/api/v1/settings/schedule', { body: change })),
    // Refresh even on failure: a version conflict means the form shows a stale schedule.
    onSettled: () => queryClient.invalidateQueries({ queryKey: SCHEDULE }),
  })
}
