import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'
import { unwrap } from '@/api/errors'
import type { components } from '@/api/schema'

type Schemas = components['schemas']
export type VocabularyTerm = Schemas['TaxonomyTermAdmin']

const TERMS = ['taxonomy-terms'] as const

/** Every role family and sector, including the ones switched off. */
export function useVocabularyTerms() {
  return useQuery({
    queryKey: TERMS,
    queryFn: () => unwrap(api.GET('/api/v1/taxonomy/terms')),
  })
}

/**
 * Add, rename, switch off and switch on. Each refreshes this list and the taxonomy the intent form
 * is built from (that one is cached for the whole session otherwise).
 */
export function useVocabularyActions() {
  const queryClient = useQueryClient()
  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: TERMS }),
      queryClient.invalidateQueries({ queryKey: ['taxonomy'] }),
    ])
  }
  const addTerm = useMutation({
    mutationFn: (body: Schemas['TaxonomyTermCreate']) =>
      unwrap(api.POST('/api/v1/taxonomy/terms', { body })),
    onSuccess: refresh,
  })
  const changeTerm = useMutation({
    mutationFn: (input: { kind: string; termKey: string } & Schemas['TaxonomyTermUpdate']) => {
      const { kind, termKey, ...body } = input
      return unwrap(
        api.PATCH('/api/v1/taxonomy/terms/{kind}/{term_key}', {
          params: { path: { kind, term_key: termKey } },
          body,
        }),
      )
    },
    onSuccess: refresh,
  })
  const mergeTerm = useMutation({
    mutationFn: (input: { kind: string; termKey: string; into: string }) =>
      unwrap(
        api.POST('/api/v1/taxonomy/terms/{kind}/{term_key}/merge', {
          params: { path: { kind: input.kind, term_key: input.termKey } },
          body: { into: input.into },
        }),
      ),
    onSuccess: refresh,
  })
  return { addTerm, changeTerm, mergeTerm }
}

/** What merging `termKey` into `into` would do to the owner's searches; runs once `into` is chosen. */
export function useMergePreview(kind: string, termKey: string, into: string) {
  return useQuery({
    queryKey: ['merge-preview', kind, termKey, into],
    enabled: into !== '',
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/taxonomy/terms/{kind}/{term_key}/merge-preview', {
          params: { path: { kind, term_key: termKey }, query: { into } },
        }),
      ),
  })
}
