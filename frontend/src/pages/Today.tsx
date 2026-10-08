import { Link } from 'react-router'
import { Button } from '@/components/ui/button'
import { useDigest } from '@/features/today/queries'
import { FitTile } from '@/features/inbox/FitTile'
import { formatAge, formatDateTime } from '@/lib/format'
import type { ReactNode } from 'react'

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section aria-labelledby={id} className="rounded-lg border border-line bg-surface">
      <h2 id={id} className="border-b border-line px-4 py-3 text-sm font-semibold">
        {title}
      </h2>
      {children}
    </section>
  )
}

const HEALTH_TEXT = {
  failed: 'Failed',
  stale: 'No recent success',
  never_run: 'Never run',
} as const

/**
 * Today: the daily digest. New recommended jobs at or above the alert threshold, shortlisted jobs
 * whose posting changed, and sources that need attention. In-app only; nothing leaves the machine.
 */
export function Today() {
  const { data, isPending, isError, refetch } = useDigest()
  if (isPending) return <p className="px-6 py-6 text-ink-3">Loading the digest…</p>
  if (isError)
    return (
      <div role="alert" className="flex items-center gap-3 px-6 py-6 text-bad">
        Could not load the digest.
        <Button variant="outline" size="sm" onClick={() => void refetch()}>
          Try again
        </Button>
      </div>
    )
  const quiet = data.counts.new_high_fit === 0 && data.counts.changed_shortlisted === 0
  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-4 px-6 py-6">
      <p className="text-ink-2">
        Since <time dateTime={data.since}>{formatDateTime(data.since)}</time>
        {data.last_run?.finished_at && (
          <> · last run finished {formatAge(data.last_run.finished_at)} ago</>
        )}
      </p>
      <Section id="fresh" title={`New matches (${data.counts.new_high_fit})`}>
        <p className="px-4 pt-3 text-xs text-ink-3">
          Recommended jobs first seen in the last 24 hours with a fit of {data.alert_threshold} or
          higher.
        </p>
        {data.new_high_fit.length === 0 ? (
          <p className="px-4 py-4 text-sm text-ink-2">
            {quiet ? 'Nothing new in the last 24 hours.' : 'No new matches.'}
          </p>
        ) : (
          <ul className="flex flex-col gap-2 p-3">
            {data.new_high_fit.map((item) => (
              <li key={item.job_inbox_item_id} className="flex items-center gap-3">
                <FitTile item={item} />
                <Link to="/inbox" className="min-w-0 font-semibold hover:underline">
                  {item.title}
                  <span className="block truncate text-[13px] font-normal text-ink-2">
                    {item.company_name}
                    {item.locations.length > 0 && ` · ${item.locations.join('; ')}`}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Section>
      <Section
        id="changed"
        title={`Shortlisted jobs that changed (${data.counts.changed_shortlisted})`}
      >
        {data.changed_shortlisted.length === 0 ? (
          <p className="px-4 py-4 text-sm text-ink-2">No shortlisted job changed.</p>
        ) : (
          <ul className="flex flex-col gap-2 p-3">
            {data.changed_shortlisted.map((entry) => (
              <li key={entry.item.job_inbox_item_id}>
                <Link to="/inbox" className="font-semibold hover:underline">
                  {entry.item.title}
                </Link>
                <span className="block text-[13px] text-ink-2">
                  {entry.item.company_name} · changed {entry.changed_fields.join(', ')} ·{' '}
                  {formatAge(entry.changed_at)} ago
                </span>
              </li>
            ))}
          </ul>
        )}
      </Section>
      <Section
        id="health"
        title={`Sources needing attention (${data.counts.sources_needing_attention})`}
      >
        {data.source_health.length === 0 ? (
          <p className="px-4 py-4 text-sm text-ink-2">All sources are healthy.</p>
        ) : (
          <ul className="flex flex-col gap-2 p-3">
            {data.source_health.map((source) => (
              <li key={source.source_configuration_id} className="text-sm">
                <Link to="/sources" className="font-semibold hover:underline">
                  {source.display_name}
                </Link>
                <span className="block text-[13px] text-ink-2">
                  {HEALTH_TEXT[source.status]}
                  {source.error_message && ` · ${source.error_message}`}
                  {source.error_class && ` (${source.error_class})`}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </div>
  )
}
