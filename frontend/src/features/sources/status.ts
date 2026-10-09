import type { CollectionRunRead, SourceRead } from './queries'

export type StatusKind =
  'running' | 'succeeded' | 'unchanged' | 'partial' | 'skipped' | 'failed' | 'never' | 'disabled'

/** Whether the active run is collecting (or will collect) this source and has no result yet. */
function isBeingCollected(source: SourceRead, run: CollectionRunRead | undefined): boolean {
  if (!run) return false
  const applies =
    run.source_configuration_id === source.source_configuration_id ||
    (run.source_configuration_id === null && source.enabled)
  const done = run.results.some((r) => r.source_configuration_id === source.source_configuration_id)
  return applies && !done
}

/** The one status word shown for a source; the reason for a failure is shown separately. */
export function statusOf(
  source: SourceRead,
  activeRun: CollectionRunRead | undefined,
): { kind: StatusKind; label: string } {
  if (isBeingCollected(source, activeRun)) return { kind: 'running', label: 'Running' }
  if (!source.enabled) return { kind: 'disabled', label: 'Disabled' }
  switch (source.last_result?.outcome) {
    case undefined:
      return { kind: 'never', label: 'Never run' }
    case 'success':
      return { kind: 'succeeded', label: 'Succeeded' }
    case 'not_modified':
      return { kind: 'unchanged', label: 'Unchanged' }
    case 'partial':
      return { kind: 'partial', label: 'Partial: limit reached' }
    case 'skipped':
      return { kind: 'skipped', label: 'Skipped: ran recently' }
    default:
      return { kind: 'failed', label: 'Failed' }
  }
}
