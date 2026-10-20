import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'
import { unwrap } from '@/api/errors'
import type { components } from '@/api/schema'

export type Pack = components['schemas']['PackRead']

const PACKS = ['packs'] as const

/** The domain packs that ship with the application and which ones are switched on. */
export function usePacks() {
  return useQuery({ queryKey: PACKS, queryFn: () => unwrap(api.GET('/api/v1/packs')) })
}

/**
 * Switch a pack on or off. The vocabulary the forms and the Vocabulary screen show depends on it,
 * so those are refreshed too.
 */
export function usePackActions() {
  const queryClient = useQueryClient()
  const setActive = useMutation({
    mutationFn: (input: { packKey: string; active: boolean }) =>
      unwrap(
        api.PUT('/api/v1/packs/{pack_key}', {
          params: { path: { pack_key: input.packKey } },
          body: { active: input.active },
        }),
      ),
    onSuccess: async () => {
      await Promise.all(
        [PACKS, ['taxonomy'], ['taxonomy-terms']].map((queryKey) =>
          queryClient.invalidateQueries({ queryKey }),
        ),
      )
    },
  })
  return { setActive }
}

const REEXTRACTION = ['re-extraction'] as const

/** How many open jobs would be analysed again with the current prompt, and for how long. */
export function useReextractionPreview(sinceDays: number) {
  return useQuery({
    queryKey: [...REEXTRACTION, sinceDays],
    retry: false,
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/pipeline/re-extraction', { params: { query: { since_days: sinceDays } } }),
      ),
  })
}

/** Queue those analyses (only after the owner confirms). */
export function useQueueReextraction() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (sinceDays: number) =>
      unwrap(api.POST('/api/v1/pipeline/re-extraction', { body: { since_days: sinceDays } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: REEXTRACTION }),
  })
}
