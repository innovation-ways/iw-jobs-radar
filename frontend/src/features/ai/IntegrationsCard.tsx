import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { useAiActions, type AiSettings } from './queries'

const field = 'rounded-md border border-line-strong bg-surface px-2.5 py-1.5 text-sm'

/**
 * Optional integrations. The GitHub token only raises GitHub's anonymous request limit for company
 * lookups; it is stored encrypted, sent once and never shown again.
 */
export function IntegrationsCard({ integrations }: { integrations: AiSettings['integrations'] }) {
  const actions = useAiActions()
  const [token, setToken] = useState('')
  const saved = integrations?.github === 'saved'
  const failure = [actions.writeIntegration, actions.removeIntegration].find(
    (m) => m.isError,
  )?.error
  return (
    <section
      aria-labelledby="integrations"
      className="rounded-lg border border-line bg-surface p-4"
    >
      <h2 id="integrations" className="text-sm font-semibold">
        Optional integrations
      </h2>
      <p className="mt-1 text-xs text-ink-3">
        Company lookups use free public datasets without a key. A GitHub token only raises
        GitHub&apos;s request limit; leave it empty if you are unsure.
      </p>
      <form
        className="mt-3 flex flex-wrap items-end gap-2.5"
        onSubmit={(event) => {
          event.preventDefault()
          if (!token.trim()) return
          actions.writeIntegration.mutate(
            { name: 'github', secret: token },
            { onSuccess: () => setToken('') },
          )
        }}
      >
        <label className="flex flex-col gap-1 text-xs text-ink-2">
          GitHub token
          <input
            className={field}
            type="password"
            autoComplete="off"
            value={token}
            placeholder={saved ? '•••••• (replace)' : ''}
            onChange={(e) => setToken(e.target.value)}
          />
        </label>
        <Button
          type="submit"
          size="sm"
          disabled={!token.trim() || actions.writeIntegration.isPending}
        >
          Save token
        </Button>
        {saved && (
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => actions.removeIntegration.mutate('github')}
          >
            Remove token
          </Button>
        )}
      </form>
      <p className="mt-2 text-xs text-ink-2">GitHub token: {saved ? 'saved' : 'not set'}</p>
      {failure && (
        <p role="alert" className="mt-2 rounded-md bg-bad-bg px-3 py-2 text-sm text-bad">
          {failure.message}
        </p>
      )}
    </section>
  )
}
