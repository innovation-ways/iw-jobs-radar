import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'
import { unwrap } from '@/api/errors'
import type { components } from '@/api/schema'

type Schemas = components['schemas']
export type Detection = Schemas['OnboardingDetectionRead']
export type DetectedBoard = Schemas['DetectedBoardRead']
export type ReaderProposal = Schemas['ReaderProposalRead']
export type OnboardingResult = Schemas['OnboardingResultRead']
export type PageReader = Schemas['PageReaderConfig']

/** What the owner types about a company (ADR-070). */
export interface FollowForm {
  name: string
  websiteUrl: string
  careersUrl: string
}

const body = (form: FollowForm) => ({
  name: form.name.trim(),
  website_url: form.websiteUrl.trim(),
  careers_url: form.careersUrl.trim(),
})

/** Check what a careers page can be collected from; nothing is saved. */
export function useDetectCompany() {
  return useMutation({
    mutationFn: (form: FollowForm) =>
      unwrap(api.POST('/api/v1/companies/onboarding/detect', { body: body(form) })),
  })
}

/** Ask the local model for a reader of a careers page that has no known board. */
export function useProposeReader() {
  return useMutation({
    mutationFn: (form: FollowForm) =>
      unwrap(api.POST('/api/v1/companies/onboarding/propose-reader', { body: body(form) })),
  })
}

/** What the owner chose to follow: a detected board, an approved reader, or neither. */
export interface FollowChoice {
  form: FollowForm
  board?: DetectedBoard
  reader?: ReaderProposal
  filtersEnabled: boolean
}

/**
 * Create the company, follow it and, with a board or a reader, add its source and queue the first
 * run. The lists, sources and runs are refreshed afterwards.
 */
export function useFollowCompany() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ form, board, reader, filtersEnabled }: FollowChoice) =>
      unwrap(
        api.POST('/api/v1/companies/onboarding', {
          body: {
            ...body(form),
            filters_enabled: filtersEnabled,
            ...(board
              ? { source: { source_type: board.source_type, identifier: board.identifier } }
              : {}),
            ...(reader ? { reader: reader.reader, reader_proposed_by: reader.proposed_by } : {}),
          },
        }),
      ),
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: ['companies'] }),
        queryClient.invalidateQueries({ queryKey: ['dossier'] }),
        queryClient.invalidateQueries({ queryKey: ['sources'] }),
        queryClient.invalidateQueries({ queryKey: ['collection-runs'] }),
      ]),
  })
}

/** Propose and approve a new reader for an existing careers-page source (after `schema_changed`). */
export function useSourceReader(sourceId: number) {
  const queryClient = useQueryClient()
  const propose = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST('/api/v1/sources/{source_configuration_id}/reader/propose', {
          params: { path: { source_configuration_id: sourceId } },
        }),
      ),
  })
  const approve = useMutation({
    mutationFn: ({ proposal, version }: { proposal: ReaderProposal; version: number }) =>
      unwrap(
        api.PUT('/api/v1/sources/{source_configuration_id}/reader', {
          params: { path: { source_configuration_id: sourceId } },
          body: {
            expected_version: version,
            reader: proposal.reader,
            proposed_by: proposal.proposed_by,
          },
        }),
      ),
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: ['dossier'] }),
        queryClient.invalidateQueries({ queryKey: ['sources'] }),
      ]),
  })
  return { propose, approve }
}

const SOURCE_LABELS: Record<string, string> = {
  greenhouse: 'Greenhouse board',
  lever: 'Lever board',
  ashby: 'Ashby board',
  smartrecruiters: 'SmartRecruiters board',
  eightfold: 'Eightfold careers site',
  page_jsonld: "Structured postings on the company's own site",
  page_config: 'Careers page with an approved reader',
}

/** The label of a source type, for the dialog and the company's collection card. */
export function sourceLabel(sourceType: string): string {
  return SOURCE_LABELS[sourceType] ?? sourceType
}
