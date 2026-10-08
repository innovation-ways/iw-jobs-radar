import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import { cn } from '@/lib/utils'

type Components = Record<string, string>
type Readiness =
  | { kind: 'ready'; components: Components }
  | { kind: 'attention'; components: Components }
  | { kind: 'unreachable' }

async function fetchReadiness(): Promise<Readiness> {
  try {
    const { data, error } = await api.GET('/readyz')
    const body = data ?? error
    if (!body) return { kind: 'unreachable' }
    return { kind: body.status === 'ready' ? 'ready' : 'attention', components: body.components }
  } catch {
    return { kind: 'unreachable' }
  }
}

function describe(components: Components): string {
  const label = (key: string) => key.charAt(0).toUpperCase() + key.slice(1)
  return Object.entries(components)
    .map(([key, state]) => `${label(key)} ${state}`)
    .join(' · ')
}

/**
 * Backend readiness shown in the sidebar footer. Status is always conveyed by text as well as
 * colour (WCAG 1.4.1), and it refreshes periodically.
 */
export function ApiStatus() {
  const { data } = useQuery({
    queryKey: ['readyz'],
    queryFn: fetchReadiness,
    refetchInterval: 15_000,
  })
  if (!data) {
    // First request still in flight: do not claim the API is down yet.
    return (
      <div role="status" className="text-xs text-ink-3">
        Checking API…
      </div>
    )
  }
  const state = data
  const headline =
    state.kind === 'ready'
      ? 'API ready'
      : state.kind === 'attention'
        ? 'Needs attention'
        : 'API unreachable'
  const tone =
    state.kind === 'ready' ? 'bg-good' : state.kind === 'attention' ? 'bg-caution' : 'bg-bad'
  return (
    <div role="status" className="text-xs text-ink-3">
      <div className="flex items-center gap-2 font-medium text-ink-2">
        <span aria-hidden="true" className={cn('size-2 rounded-full', tone)} />
        {state.kind === 'attention' && <span className="sr-only">Warning: </span>}
        {headline}
      </div>
      {state.kind !== 'unreachable' && <div className="mt-0.5">{describe(state.components)}</div>}
    </div>
  )
}
