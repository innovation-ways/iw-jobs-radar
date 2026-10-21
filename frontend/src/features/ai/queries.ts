import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'
import { unwrap } from '@/api/errors'
import type { components } from '@/api/schema'

type Schemas = components['schemas']
export type AiSettings = Schemas['AiSettingsRead']
export type Connection = Schemas['ConnectionRead']
export type ConnectionTest = Schemas['ConnectionTestRead']
export type ProviderType = Connection['provider_type']

const AI = ['ai-settings'] as const

/** The safe projection of the AI & privacy configuration (credentials are never included). */
export function useAiSettings() {
  return useQuery({ queryKey: AI, queryFn: () => unwrap(api.GET('/api/v1/settings/ai')) })
}

/** Mutations of the AI & privacy screen; each refreshes the configuration it changed. */
export function useAiActions() {
  const queryClient = useQueryClient()
  const refresh = () => queryClient.invalidateQueries({ queryKey: AI })
  const path = (id: number) => ({ params: { path: { provider_connection_id: id } } })

  const createConnection = useMutation({
    mutationFn: (body: Schemas['ConnectionCreate']) =>
      unwrap(api.POST('/api/v1/settings/ai/connections', { body })),
    onSuccess: refresh,
  })
  const updateConnection = useMutation({
    mutationFn: (change: { id: number } & Schemas['ConnectionUpdate']) => {
      const { id, ...body } = change
      return unwrap(
        api.PUT('/api/v1/settings/ai/connections/{provider_connection_id}', {
          ...path(id),
          body,
        }),
      )
    },
    onSettled: refresh,
  })
  const deleteConnection = useMutation({
    mutationFn: (id: number) =>
      unwrap(api.DELETE('/api/v1/settings/ai/connections/{provider_connection_id}', path(id))),
    onSettled: refresh,
  })
  const writeCredential = useMutation({
    mutationFn: (input: { id: number; secret: string }) =>
      unwrap(
        api.PUT('/api/v1/settings/ai/connections/{provider_connection_id}/credential', {
          ...path(input.id),
          body: { secret: input.secret },
        }),
      ),
    onSettled: refresh,
  })
  const removeCredential = useMutation({
    mutationFn: (id: number) =>
      unwrap(
        api.DELETE('/api/v1/settings/ai/connections/{provider_connection_id}/credential', path(id)),
      ),
    onSettled: refresh,
  })
  const testConnection = useMutation({
    mutationFn: (id: number) =>
      unwrap(api.POST('/api/v1/settings/ai/connections/{provider_connection_id}/test', path(id))),
  })
  const selectImport = useMutation({
    mutationFn: (id: number | null) =>
      unwrap(
        api.PUT('/api/v1/settings/ai/import-connection', {
          body: { provider_connection_id: id },
        }),
      ),
    onSettled: refresh,
  })
  const selectJobs = useMutation({
    mutationFn: (id: number | null) =>
      unwrap(
        api.PUT('/api/v1/settings/ai/jobs-connection', { body: { provider_connection_id: id } }),
      ),
    onSettled: refresh,
  })
  const updatePrivacy = useMutation({
    // `allowLocal` is left out to keep that switch as it is (ADR-081).
    mutationFn: (change: { redact: boolean; allowLocal?: boolean; version: number }) =>
      unwrap(
        api.PUT('/api/v1/settings/privacy', {
          body: {
            redact_contact_details: change.redact,
            ...(change.allowLocal === undefined
              ? {}
              : { allow_local_providers: change.allowLocal }),
            expected_version: change.version,
          },
        }),
      ),
    onSettled: refresh,
  })
  const writeIntegration = useMutation({
    mutationFn: (input: { name: string; secret: string }) =>
      unwrap(
        api.PUT('/api/v1/settings/integrations/{name}/credential', {
          params: { path: { name: input.name } },
          body: { secret: input.secret },
        }),
      ),
    onSettled: refresh,
  })
  const removeIntegration = useMutation({
    mutationFn: (name: string) =>
      unwrap(
        api.DELETE('/api/v1/settings/integrations/{name}/credential', {
          params: { path: { name } },
        }),
      ),
    onSettled: refresh,
  })
  return {
    writeIntegration,
    removeIntegration,
    createConnection,
    updateConnection,
    deleteConnection,
    writeCredential,
    removeCredential,
    testConnection,
    selectImport,
    selectJobs,
    updatePrivacy,
  }
}
