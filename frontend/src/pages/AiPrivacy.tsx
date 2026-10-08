import { AddConnectionForm } from '@/features/ai/AddConnectionForm'
import { ConnectionCard } from '@/features/ai/ConnectionCard'
import { useAiActions, useAiSettings, type AiSettings } from '@/features/ai/queries'
import { Button } from '@/components/ui/button'

const field = 'rounded-md border border-line-strong bg-surface px-2.5 py-1.5 text-sm'

const MODE_TEXT: Record<AiSettings['mode'], string> = {
  no_ai:
    'No AI. Jobs are still collected, grouped and listed as “not evaluated”; CVs cannot be imported.',
  local: 'Processing happens on this machine. Nothing leaves your network.',
  remote:
    'CV import uses a remote provider. Only text with contact details removed is sent, after you confirm each CV.',
}

/**
 * AI & privacy: where processing happens, the connections and their write-only credentials, which
 * connection imports CVs, which local model analyses jobs, and the redaction policy. The default
 * is No AI; job text is only ever analysed by a local model.
 */
export function AiPrivacy() {
  const { data, isPending, isError, refetch } = useAiSettings()
  const actions = useAiActions()
  if (isPending) return <p className="px-6 py-6 text-ink-3">Loading…</p>
  if (isError)
    return (
      <div role="alert" className="flex items-center gap-3 px-6 py-6 text-bad">
        Could not load the settings.
        <Button variant="outline" size="sm" onClick={() => void refetch()}>
          Try again
        </Button>
      </div>
    )
  const usable = data.connections.filter(
    (c) => c.model_id && (c.processing_location === 'local' || c.credential_status === 'saved'),
  )
  const local = data.connections.filter((c) => c.processing_location === 'local' && c.model_id)
  const failure = [actions.selectImport, actions.selectJobs, actions.updatePrivacy].find(
    (mutation) => mutation.isError,
  )?.error

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-4 px-6 py-6">
      {!data.key_configured && (
        <p role="alert" className="rounded-md bg-bad-bg px-3.5 py-2 text-sm text-bad">
          JOBS_RADAR_CREDENTIAL_KEY is not configured, so API keys cannot be stored. Run
          ./jobs-radar.sh --init-env, restart the services and try again.
        </p>
      )}
      <section className="rounded-lg border border-line bg-surface p-4" aria-labelledby="mode">
        <h2 id="mode" className="text-sm font-semibold">
          Where processing happens
        </h2>
        <p className="mt-2 text-sm text-ink-2">{MODE_TEXT[data.mode]}</p>
        <div className="mt-3 flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-xs text-ink-2">
            CV import
            <select
              className={field}
              value={data.import_connection_id ?? ''}
              onChange={(e) =>
                actions.selectImport.mutate(e.target.value ? Number(e.target.value) : null)
              }
            >
              <option value="">No AI</option>
              {usable.map((c) => (
                <option key={c.provider_connection_id} value={c.provider_connection_id}>
                  {c.display_name} · {c.processing_location === 'local' ? 'this machine' : 'remote'}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs text-ink-2">
            Job analysis
            <select
              className={field}
              value={data.jobs_connection_id ?? ''}
              onChange={(e) =>
                actions.selectJobs.mutate(e.target.value ? Number(e.target.value) : null)
              }
            >
              <option value="">No AI</option>
              {local.map((c) => (
                <option key={c.provider_connection_id} value={c.provider_connection_id}>
                  {c.display_name} · {c.model_id}
                </option>
              ))}
            </select>
          </label>
        </div>
        <p className="mt-2 text-xs text-ink-3">
          Job text is only analysed by a local model; it is never sent to a remote provider.
        </p>
        {failure && (
          <p role="alert" className="mt-3 rounded-md bg-bad-bg px-3 py-2 text-sm text-bad">
            {failure.message}
          </p>
        )}
      </section>

      {data.connections.map((connection) => (
        <ConnectionCard key={connection.provider_connection_id} connection={connection} />
      ))}

      <section className="rounded-lg border border-line bg-surface p-4" aria-labelledby="add">
        <h2 id="add" className="mb-3 text-sm font-semibold">
          Add a connection
        </h2>
        <AddConnectionForm />
      </section>

      <section className="rounded-lg border border-line bg-surface p-4" aria-labelledby="privacy">
        <h2 id="privacy" className="text-sm font-semibold">
          Privacy
        </h2>
        <ul className="mt-2 flex flex-col gap-2 text-sm">
          <li>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={data.privacy.redact_contact_details}
                onChange={(e) =>
                  actions.updatePrivacy.mutate({
                    redact: e.target.checked,
                    version: data.privacy.version,
                  })
                }
              />
              Remove contact details (e-mail, phone, links) before any remote call
            </label>
          </li>
          <li className="text-ink-2">
            Every CV needs your confirmation before it goes to a remote provider.
          </li>
          <li className="text-ink-2">Uploaded CVs are never stored.</li>
        </ul>
      </section>
    </div>
  )
}
