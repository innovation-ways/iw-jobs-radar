import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'
import { unwrap } from '@/api/errors'
import type { components } from '@/api/schema'

type Schemas = components['schemas']
export type ProfileRead = Schemas['ProfileRead']
export type ProfileRevisionRead = Schemas['ProfileRevisionRead']
export type ProfileRevisionSummary = Schemas['ProfileRevisionSummary']
export type ProfileSave = Schemas['ProfileSave']
export type IntentRead = Schemas['IntentRead']
export type IntentRevisionRead = Schemas['IntentRevisionRead']
export type IntentDefinition = Schemas['IntentDefinition']
export type TaxonomyRead = Schemas['TaxonomyRead']
export type PlaceRead = Schemas['PlaceRead']

const PROFILES = ['profiles'] as const
const intentsKey = (profileId: number) => ['intents', profileId] as const
const profileRevisionsKey = (profileId: number) => ['profile-revisions', profileId] as const
const intentRevisionsKey = (intentId: number) => ['intent-revisions', intentId] as const

/** Every profile with its current revision. */
export function useProfiles() {
  return useQuery({
    queryKey: PROFILES,
    queryFn: async () => (await unwrap(api.GET('/api/v1/profiles'))).items,
  })
}

/** The intents of one profile; disabled until a profile is selected. */
export function useIntents(profileId: number | undefined) {
  return useQuery({
    queryKey: intentsKey(profileId ?? 0),
    enabled: profileId !== undefined,
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/profiles/{career_profile_id}/intents', {
            params: { path: { career_profile_id: profileId! } },
          }),
        )
      ).items,
  })
}

/** The controlled vocabularies (rarely change, so cached for the session). */
export function useTaxonomy() {
  return useQuery({
    queryKey: ['taxonomy'],
    staleTime: Infinity,
    queryFn: () => unwrap(api.GET('/api/v1/taxonomy')),
  })
}

export function useProfileRevisions(profileId: number | undefined) {
  return useQuery({
    queryKey: profileRevisionsKey(profileId ?? 0),
    enabled: profileId !== undefined,
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/profiles/{career_profile_id}/revisions', {
            params: { path: { career_profile_id: profileId! } },
          }),
        )
      ).items,
  })
}

export function useIntentRevisions(intentId: number | undefined) {
  return useQuery({
    queryKey: intentRevisionsKey(intentId ?? 0),
    enabled: intentId !== undefined,
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/api/v1/intents/{search_intent_id}/revisions', {
            params: { path: { search_intent_id: intentId! } },
          }),
        )
      ).items,
  })
}

/** Fetch one profile revision (used by History to view and compare). */
export function fetchProfileRevision(profileId: number, revisionId: number) {
  return unwrap(
    api.GET('/api/v1/profiles/{career_profile_id}/revisions/{profile_revision_id}', {
      params: { path: { career_profile_id: profileId, profile_revision_id: revisionId } },
    }),
  )
}

/** Search cities offline by name prefix. */
export function searchPlaces(query: string, country?: string) {
  return unwrap(
    api.GET('/api/v1/locations/search', {
      params: { query: { q: query, limit: 8, ...(country ? { country } : {}) } },
    }),
  ).then((result) => result.items)
}

/** Mutations of profiles and intents; each refreshes the lists it affects. */
export function useProfileActions() {
  const queryClient = useQueryClient()
  const profileChanged = (profileId: number) =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: PROFILES }),
      queryClient.invalidateQueries({ queryKey: profileRevisionsKey(profileId) }),
    ])
  const intentChanged = (profileId: number, intentId: number) =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: intentsKey(profileId) }),
      queryClient.invalidateQueries({ queryKey: intentRevisionsKey(intentId) }),
    ])

  const createProfile = useMutation({
    mutationFn: (title: string) =>
      unwrap(api.POST('/api/v1/profiles', { body: { title, visibility: 'private' } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: PROFILES }),
  })
  const saveProfile = useMutation({
    mutationFn: (input: { profileId: number; body: ProfileSave }) =>
      unwrap(
        api.PUT('/api/v1/profiles/{career_profile_id}', {
          params: { path: { career_profile_id: input.profileId } },
          body: input.body,
        }),
      ),
    // Refresh on failure too: a conflict means what is on screen is out of date.
    onSettled: (_data, _error, input) => profileChanged(input.profileId),
  })
  const restoreProfile = useMutation({
    mutationFn: (input: { profileId: number; revisionId: number; expected: number }) =>
      unwrap(
        api.POST('/api/v1/profiles/{career_profile_id}/revisions/{profile_revision_id}/restore', {
          params: {
            path: { career_profile_id: input.profileId, profile_revision_id: input.revisionId },
          },
          body: { expected_current_revision: input.expected },
        }),
      ),
    onSettled: (_data, _error, input) => profileChanged(input.profileId),
  })
  const createIntent = useMutation({
    mutationFn: (input: { profileId: number; definition: IntentDefinition }) =>
      unwrap(
        api.POST('/api/v1/profiles/{career_profile_id}/intents', {
          params: { path: { career_profile_id: input.profileId } },
          body: { ...input.definition, enabled: true },
        }),
      ),
    onSuccess: (_data, input) =>
      queryClient.invalidateQueries({ queryKey: intentsKey(input.profileId) }),
  })
  const saveIntent = useMutation({
    mutationFn: (input: {
      profileId: number
      intentId: number
      definition: IntentDefinition
      expected: number
      summary?: string
    }) =>
      unwrap(
        api.PUT('/api/v1/intents/{search_intent_id}', {
          params: { path: { search_intent_id: input.intentId } },
          body: {
            ...input.definition,
            expected_current_revision: input.expected,
            change_summary: input.summary ?? null,
          },
        }),
      ),
    onSettled: (_data, _error, input) => intentChanged(input.profileId, input.intentId),
  })
  const setIntentEnabled = useMutation({
    mutationFn: (input: {
      profileId: number
      intentId: number
      version: number
      enabled: boolean
    }) =>
      unwrap(
        api.POST(
          input.enabled
            ? '/api/v1/intents/{search_intent_id}/enable'
            : '/api/v1/intents/{search_intent_id}/disable',
          {
            params: { path: { search_intent_id: input.intentId } },
            body: { expected_version: input.version },
          },
        ),
      ),
    onSettled: (_data, _error, input) => intentChanged(input.profileId, input.intentId),
  })
  const restoreIntent = useMutation({
    mutationFn: (input: {
      profileId: number
      intentId: number
      revisionId: number
      expected: number
    }) =>
      unwrap(
        api.POST('/api/v1/intents/{search_intent_id}/revisions/{intent_revision_id}/restore', {
          params: {
            path: { search_intent_id: input.intentId, intent_revision_id: input.revisionId },
          },
          body: { expected_current_revision: input.expected },
        }),
      ),
    onSettled: (_data, _error, input) => intentChanged(input.profileId, input.intentId),
  })
  return {
    createProfile,
    saveProfile,
    restoreProfile,
    createIntent,
    saveIntent,
    setIntentEnabled,
    restoreIntent,
  }
}
