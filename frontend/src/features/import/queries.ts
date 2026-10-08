import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'
import { describeApiError, unwrap, ApiError } from '@/api/errors'
import type { components } from '@/api/schema'

type Schemas = components['schemas']
export type DocumentRead = Schemas['DocumentRead']
export type ProposalRead = Schemas['ProposalRead']
export type ProposalItem = Schemas['ProposalItemRead']
export type Decision = Schemas['DecisionRequest']

/**
 * Upload a CV as multipart form data. The endpoint is not part of the typed client (a file part
 * has no JSON schema), so it uses `fetch` and the same error envelope handling.
 */
async function uploadDocument(file: File): Promise<DocumentRead> {
  const form = new FormData()
  form.append('file', file)
  let response: Response
  try {
    response = await fetch('/api/v1/documents', { method: 'POST', body: form })
  } catch (error) {
    throw new ApiError(describeApiError(error).message)
  }
  const body: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const { message, errorClass } = describeApiError(body)
    throw new ApiError(message, errorClass)
  }
  return body as DocumentRead
}

/** Mutations of the CV import flow. */
export function useImportActions(profileId: number) {
  const queryClient = useQueryClient()
  const upload = useMutation({ mutationFn: uploadDocument })
  const propose = useMutation({
    mutationFn: (input: {
      documentId: number
      consent: { provider_connection_id: number; model_id: string } | null
    }) =>
      unwrap(
        api.POST('/api/v1/documents/{document_id}/proposals', {
          params: { path: { document_id: input.documentId } },
          body: { career_profile_id: profileId, consent: input.consent },
        }),
      ),
  })
  const review = useMutation({
    mutationFn: (input: {
      proposalId: number
      expectedRevision: number | null
      decisions: Decision[]
    }) =>
      unwrap(
        api.POST('/api/v1/profiles/{career_profile_id}/reviews', {
          params: { path: { career_profile_id: profileId } },
          body: {
            profile_proposal_id: input.proposalId,
            expected_current_revision: input.expectedRevision,
            decisions: input.decisions,
          },
        }),
      ),
    // The profile (and its history) changed when a revision was created.
    onSettled: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: ['profiles'] }),
        queryClient.invalidateQueries({ queryKey: ['profile-revisions', profileId] }),
      ]),
  })
  return { upload, propose, review }
}
