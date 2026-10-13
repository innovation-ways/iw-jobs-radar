import { formatDateTime } from '@/lib/format'
import type { CollectionRunRead } from './queries'

const STATUS: Record<string, string> = {
  queued: 'Queued',
  running: 'Running',
  succeeded: 'Succeeded',
  partial: 'Partly succeeded',
  failed: 'Failed',
  cancelled: 'Cancelled',
}

/** The latest collection runs: when, how it was started, the outcome and why it failed. */
export function RunHistory({ runs }: { runs: CollectionRunRead[] }) {
  return (
    <section aria-labelledby="runs" className="rounded-lg border border-line bg-surface">
      <h2 id="runs" className="border-b border-line px-4 py-3 text-sm font-semibold">
        Recent runs
      </h2>
      {runs.length === 0 ? (
        <p className="px-4 py-4 text-sm text-ink-2">No runs yet.</p>
      ) : (
        <div className="relative overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="sr-only">
              <tr>
                <th>Requested</th>
                <th>Trigger</th>
                <th>Outcome</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.collection_run_id} className="border-t border-line first:border-t-0">
                  <td className="px-4 py-2">
                    <time dateTime={run.requested_at}>{formatDateTime(run.requested_at)}</time>
                  </td>
                  <td className="px-2 py-2">
                    {run.trigger === 'scheduled' ? 'Scheduled' : 'Manual'}
                    {run.source_configuration_id !== null && ' · one board'}
                  </td>
                  <td className="px-2 py-2 font-medium">{STATUS[run.status] ?? run.status}</td>
                  <td className="px-4 py-2 text-ink-2">
                    {run.error_class
                      ? `Reason: ${run.error_class}`
                      : `${run.results.length} boards`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
