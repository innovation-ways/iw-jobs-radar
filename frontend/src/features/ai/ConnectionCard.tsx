import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { useAiActions, type Connection } from './queries'

const field = 'rounded-md border border-line-strong bg-surface px-2.5 py-1.5 text-sm'

/**
 * One AI connection: its non-secret settings, a write-only credential, a connection test with
 * model discovery (or a typed model id when the provider cannot list models) and removal.
 * The key is typed into a password field, sent once and cleared; it is never shown again.
 */
export function ConnectionCard({ connection }: { connection: Connection }) {
  const actions = useAiActions()
  const [secret, setSecret] = useState('')
  const [model, setModel] = useState(connection.model_id ?? '')
  const [directionModel, setDirectionModel] = useState(connection.direction_model ?? '')
  const remote = connection.processing_location === 'remote'
  const test = actions.testConnection.data
  const saved = connection.credential_status === 'saved'
  const failure = [
    actions.writeCredential,
    actions.removeCredential,
    actions.updateConnection,
    actions.deleteConnection,
  ].find((mutation) => mutation.isError)?.error

  return (
    <section
      aria-labelledby={`connection-${connection.provider_connection_id}`}
      className="rounded-lg border border-line bg-surface p-4"
    >
      <div className="flex flex-wrap items-center gap-2">
        <h3
          id={`connection-${connection.provider_connection_id}`}
          className="text-sm font-semibold"
        >
          {connection.display_name}
        </h3>
        <span className="rounded bg-surface-2 px-1.5 text-xs text-ink-2">
          {connection.provider_type} · {remote ? 'remote' : 'this machine'}
        </span>
        <Button
          className="ml-auto"
          variant="ghost"
          size="sm"
          onClick={() => {
            if (window.confirm(`Delete the connection “${connection.display_name}”?`))
              actions.deleteConnection.mutate(connection.provider_connection_id)
          }}
        >
          Delete
        </Button>
      </div>
      <p className="mt-1 text-xs break-all text-ink-3">{connection.endpoint_url}</p>

      <div className="mt-3 flex flex-wrap items-end gap-2.5">
        <label className="flex flex-col gap-1 text-xs text-ink-2">
          Model
          {test?.ok && test.models.length > 0 ? (
            <select className={field} value={model} onChange={(e) => setModel(e.target.value)}>
              {!test.models.includes(model) && model && <option value={model}>{model}</option>}
              {test.models.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          ) : (
            <input
              className={field}
              value={model}
              placeholder="model id"
              onChange={(e) => setModel(e.target.value)}
            />
          )}
        </label>
        <Button
          size="sm"
          variant="outline"
          disabled={model === (connection.model_id ?? '') || actions.updateConnection.isPending}
          onClick={() =>
            actions.updateConnection.mutate({
              id: connection.provider_connection_id,
              expected_version: connection.version,
              model_id: model,
            })
          }
        >
          Save model
        </Button>
        <Button
          size="sm"
          variant="outline"
          disabled={actions.testConnection.isPending || (remote && !saved)}
          onClick={() => actions.testConnection.mutate(connection.provider_connection_id)}
        >
          Test connection
        </Button>
      </div>

      {!remote && (
        <div className="mt-3 flex flex-wrap items-end gap-2.5">
          <label className="flex flex-col gap-1 text-xs text-ink-2">
            Model for career directions
            <input
              className={field}
              value={directionModel}
              placeholder="same as the model above"
              onChange={(e) => setDirectionModel(e.target.value)}
            />
          </label>
          <Button
            size="sm"
            variant="outline"
            disabled={
              directionModel === (connection.direction_model ?? '') ||
              actions.updateConnection.isPending
            }
            onClick={() =>
              actions.updateConnection.mutate({
                id: connection.provider_connection_id,
                expected_version: connection.version,
                direction_model: directionModel,
              })
            }
          >
            Save directions model
          </Button>
          <p className="basis-full text-xs text-ink-3">
            Optional. A larger local model judges how well a job fits your career directions; the
            smaller one above keeps reading the jobs. Leave empty to use the same model.
          </p>
        </div>
      )}

      {remote && (
        <form
          className="mt-3 flex flex-wrap items-end gap-2.5"
          onSubmit={(event) => {
            event.preventDefault()
            if (!secret.trim()) return
            actions.writeCredential.mutate(
              { id: connection.provider_connection_id, secret },
              { onSuccess: () => setSecret('') },
            )
          }}
        >
          <label className="flex flex-col gap-1 text-xs text-ink-2">
            API key
            <input
              className={field}
              type="password"
              autoComplete="off"
              value={secret}
              placeholder={saved ? '•••••• (replace)' : ''}
              onChange={(e) => setSecret(e.target.value)}
            />
          </label>
          <Button
            type="submit"
            size="sm"
            disabled={!secret.trim() || actions.writeCredential.isPending}
          >
            Save key
          </Button>
          {saved && (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={() => actions.removeCredential.mutate(connection.provider_connection_id)}
            >
              Remove key
            </Button>
          )}
        </form>
      )}
      {remote && (
        <p className="mt-2 text-xs text-ink-2">Credential: {saved ? 'saved' : 'not set'}</p>
      )}

      {test && (
        <p
          role={test.ok ? 'status' : 'alert'}
          className={`mt-3 rounded-md px-3 py-2 text-sm ${test.ok ? 'bg-good-bg text-good' : 'bg-bad-bg text-bad'}`}
        >
          {test.message}
          {!test.ok && test.error_class && ` (${test.error_class})`}
        </p>
      )}
      {failure && (
        <p role="alert" className="mt-3 rounded-md bg-bad-bg px-3 py-2 text-sm text-bad">
          {failure.message}
        </p>
      )}
    </section>
  )
}
