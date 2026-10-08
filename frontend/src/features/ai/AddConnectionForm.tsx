import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { useAiActions, type ProviderType } from './queries'

const field = 'rounded-md border border-line-strong bg-surface px-2.5 py-1.5 text-sm'
const TYPES: { value: ProviderType; label: string }[] = [
  { value: 'ollama', label: 'Local · Ollama' },
  { value: 'openai', label: 'OpenAI' },
  { value: 'minimax', label: 'MiniMax' },
  { value: 'compatible', label: 'Compatible endpoint' },
]
const NEEDS_ENDPOINT: ProviderType[] = ['minimax', 'compatible']

/** Form that adds a connection; the key is entered afterwards, on the connection's own card. */
export function AddConnectionForm() {
  const { createConnection } = useAiActions()
  const [type, setType] = useState<ProviderType>('ollama')
  const [name, setName] = useState('')
  const [endpoint, setEndpoint] = useState('')
  const [model, setModel] = useState('')

  return (
    <form
      className="flex flex-wrap items-end gap-2.5"
      onSubmit={(event) => {
        event.preventDefault()
        createConnection.mutate(
          {
            provider_type: type,
            display_name: name.trim(),
            endpoint_url: endpoint.trim() || null,
            model_id: model.trim() || null,
          },
          {
            onSuccess: () => {
              setName('')
              setEndpoint('')
              setModel('')
            },
          },
        )
      }}
    >
      <label className="flex flex-col gap-1 text-xs text-ink-2">
        Provider
        <select
          className={field}
          value={type}
          onChange={(e) => setType(e.target.value as ProviderType)}
        >
          {TYPES.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-xs text-ink-2">
        Name
        <input
          className={field}
          value={name}
          maxLength={120}
          onChange={(e) => setName(e.target.value)}
        />
      </label>
      {NEEDS_ENDPOINT.includes(type) && (
        <label className="flex flex-col gap-1 text-xs text-ink-2">
          Endpoint URL (https)
          <input className={field} value={endpoint} onChange={(e) => setEndpoint(e.target.value)} />
        </label>
      )}
      <label className="flex flex-col gap-1 text-xs text-ink-2">
        Model
        <input className={field} value={model} onChange={(e) => setModel(e.target.value)} />
      </label>
      <Button type="submit" disabled={!name.trim() || createConnection.isPending}>
        Add connection
      </Button>
      {createConnection.isError && (
        <p role="alert" className="basis-full text-sm text-bad">
          {createConnection.error.message}
        </p>
      )}
    </form>
  )
}
