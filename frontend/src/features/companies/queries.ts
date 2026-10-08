import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'
import { unwrap } from '@/api/errors'
import type { components } from '@/api/schema'

type Schemas = components['schemas']
export type CompanySummary = Schemas['CompanySummary']
export type Dossier = Schemas['CompanyDossierRead']
export type WindowDays = 7 | 15 | 30

interface ListParams {
  q: string
  window: WindowDays
  relevantOnly: boolean
  limit: number
}

/** The company list for a window; kept on screen while the next page of results loads. */
export function useCompanies({ q, window, relevantOnly, limit }: ListParams) {
  return useQuery({
    queryKey: ['companies', q, window, relevantOnly, limit],
    placeholderData: keepPreviousData,
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/companies', {
          params: {
            query: {
              window,
              sort: 'new',
              limit,
              ...(q ? { q } : {}),
              ...(relevantOnly ? { relevant_only: true } : {}),
            },
          },
        }),
      ),
  })
}

const dossierKey = (id: number) => ['dossier', id] as const

/** One company's dossier. */
export function useDossier(companyId: number | null) {
  return useQuery({
    queryKey: dossierKey(companyId ?? 0),
    enabled: companyId !== null,
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/companies/{company_id}', {
          params: { path: { company_id: companyId! } },
        }),
      ),
  })
}

/** Actions on a dossier; each returns the refreshed dossier. */
export function useDossierActions(companyId: number) {
  const queryClient = useQueryClient()
  const path = { params: { path: { company_id: companyId } } }
  const store = (dossier: Dossier) => {
    queryClient.setQueryData(dossierKey(companyId), dossier)
    return queryClient.invalidateQueries({ queryKey: ['companies'] })
  }
  const enrich = useMutation({
    mutationFn: () => unwrap(api.POST('/api/v1/companies/{company_id}/enrich', path)),
    onSuccess: store,
  })
  const summarise = useMutation({
    mutationFn: () => unwrap(api.POST('/api/v1/companies/{company_id}/summary', path)),
    onSuccess: store,
  })
  const decide = useMutation({
    mutationFn: (input: { candidateId: number; decision: 'confirm' | 'reject' }) => {
      const params = {
        params: {
          path: { company_id: companyId, company_enrichment_candidate_id: input.candidateId },
        },
      }
      return input.decision === 'confirm'
        ? unwrap(
            api.POST(
              '/api/v1/companies/{company_id}/candidates/{company_enrichment_candidate_id}/confirm',
              params,
            ),
          )
        : unwrap(
            api.POST(
              '/api/v1/companies/{company_id}/candidates/{company_enrichment_candidate_id}/reject',
              params,
            ),
          )
    },
    onSuccess: store,
  })
  return { enrich, summarise, decide }
}
