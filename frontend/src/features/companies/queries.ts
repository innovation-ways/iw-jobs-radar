import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'
import { unwrap } from '@/api/errors'
import type { components } from '@/api/schema'
import type { OwnerAction } from '@/features/inbox/undo'

type Schemas = components['schemas']
export type CompanySummary = Schemas['CompanySummary']
export type Dossier = Schemas['CompanyDossierRead']
export type Offer = Schemas['OfferRead']

export type CompanySort = 'newest' | 'recommended' | 'fit' | 'name'

interface ListParams {
  q: string
  sort: CompanySort
  hideIgnored: boolean
  ignoredOnly?: boolean
  openOnly: boolean
  recommendedOnly: boolean
  pendingOnly: boolean
  limit: number
}

/** The company list: followed first, then in the chosen order (newest offers by default). */
export function useCompanies({
  q,
  sort,
  hideIgnored,
  ignoredOnly = false,
  openOnly,
  recommendedOnly,
  pendingOnly,
  limit,
}: ListParams) {
  return useQuery({
    queryKey: [
      'companies',
      q,
      sort,
      hideIgnored,
      ignoredOnly,
      openOnly,
      recommendedOnly,
      pendingOnly,
      limit,
    ],
    placeholderData: keepPreviousData,
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/companies', {
          params: {
            query: {
              limit,
              ...(q ? { q } : {}),
              sort,
              ...(hideIgnored ? { hide_ignored: true } : {}),
              ...(ignoredOnly ? { ignored_only: true } : {}),
              ...(openOnly ? { open_only: true } : {}),
              ...(recommendedOnly ? { recommended_only: true } : {}),
              ...(pendingOnly ? { pending_only: true } : {}),
            },
          },
        }),
      ),
  })
}

/** Follow or unfollow a company; the list and the dossier refresh afterwards. */
export function useFollow() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ companyId, follow }: { companyId: number; follow: boolean }) => {
      const params = { params: { path: { company_id: companyId } } }
      return follow
        ? unwrap(api.PUT('/api/v1/companies/{company_id}/follow', params))
        : unwrap(api.DELETE('/api/v1/companies/{company_id}/follow', params))
    },
    onSuccess: (_state, { companyId }) =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: ['companies'] }),
        queryClient.invalidateQueries({ queryKey: ['dossier', companyId] }),
      ]),
  })
}

/** Ignore or stop ignoring a company; its offers move at once, so the inbox refreshes too. */
export function useIgnoreCompany() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ companyId, ignore }: { companyId: number; ignore: boolean }) => {
      const params = { params: { path: { company_id: companyId } } }
      return ignore
        ? unwrap(api.PUT('/api/v1/companies/{company_id}/ignore', params))
        : unwrap(api.DELETE('/api/v1/companies/{company_id}/ignore', params))
    },
    onSuccess: (_state, { companyId }) =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: ['companies'] }),
        queryClient.invalidateQueries({ queryKey: ['dossier', companyId] }),
        queryClient.invalidateQueries({ queryKey: ['inbox'] }),
      ]),
  })
}

const dossierKey = (id: number, includeOlder = false) => ['dossier', id, includeOlder] as const

/** One company's dossier; `includeOlder` adds the offers beyond the recency limit. */
export function useDossier(companyId: number | null, includeOlder = false) {
  return useQuery({
    queryKey: dossierKey(companyId ?? 0, includeOlder),
    enabled: companyId !== null,
    placeholderData: keepPreviousData,
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/companies/{company_id}', {
          params: {
            path: { company_id: companyId! },
            query: includeOlder ? { include_older: true } : {},
          },
        }),
      ),
  })
}

/** Actions on a dossier; each returns the refreshed dossier. */
export function useDossierActions(companyId: number) {
  const queryClient = useQueryClient()
  const path = { params: { path: { company_id: companyId } } }
  const store = (dossier: Dossier) => {
    // The action returns the dossier without older offers; other variants are refetched.
    queryClient.setQueryData(dossierKey(companyId), dossier)
    return Promise.all([
      queryClient.invalidateQueries({ queryKey: ['dossier', companyId] }),
      queryClient.invalidateQueries({ queryKey: ['companies'] }),
    ])
  }
  const enrich = useMutation({
    mutationFn: () => unwrap(api.POST('/api/v1/companies/{company_id}/enrich', path)),
    onSuccess: store,
  })
  const summarise = useMutation({
    mutationFn: () => unwrap(api.POST('/api/v1/companies/{company_id}/summary', path)),
    onSuccess: store,
  })
  const analyse = useMutation({
    mutationFn: () => unwrap(api.POST('/api/v1/companies/{company_id}/analyse', path)),
    onSuccess: store,
  })
  const setWebsite = useMutation({
    mutationFn: (url: string) =>
      unwrap(api.PUT('/api/v1/companies/{company_id}/website', { ...path, body: { url } })),
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
  return { enrich, summarise, analyse, setWebsite, decide }
}

/**
 * Triage of one offer from the dossier, through the same inbox action endpoint the Inbox uses (so
 * the transitions, events and optimistic concurrency are identical). Whatever the outcome, the
 * dossier, the company list counts and the inbox are refetched: a conflict means the screen is out
 * of date, and ignoring or restoring an offer changes what the list counts.
 */
export function useOfferActions() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: { itemId: number; action: OwnerAction; version: number }) =>
      unwrap(
        api.POST('/api/v1/inbox/{job_inbox_item_id}/actions', {
          params: { path: { job_inbox_item_id: input.itemId }, query: {} },
          body: { action: input.action, expected_version: input.version },
        }),
      ),
    onSettled: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: ['inbox'] }),
        queryClient.invalidateQueries({ queryKey: ['dossier'] }),
        queryClient.invalidateQueries({ queryKey: ['companies'] }),
      ]),
  })
}
