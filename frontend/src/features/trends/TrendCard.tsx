import { formatPoints, percent } from './format'
import { Sparkline } from './Sparkline'
import { useTrends, type TermKind } from './queries'

/** One ranked table: open relevant jobs per term, its share, the change and a sparkline. */
export function TrendCard({
  kind,
  title,
  weeks,
}: {
  kind: TermKind
  title: string
  weeks: number
}) {
  const { data, isPending, isError, error } = useTrends(kind, weeks)
  return (
    <section aria-labelledby={`trend-${kind}`} className="rounded-lg border border-line bg-surface">
      <div className="flex items-baseline justify-between border-b border-line px-4 py-3">
        <h3 id={`trend-${kind}`} className="text-sm font-semibold">
          {title}
        </h3>
        <span className="text-xs text-ink-3">open relevant jobs</span>
      </div>
      {isPending && <p className="px-4 py-4 text-sm text-ink-3">Loading…</p>}
      {isError && <p className="px-4 py-4 text-sm text-ink-2">{error.message}</p>}
      {data && data.rows.length === 0 && (
        <p className="px-4 py-4 text-sm text-ink-2">
          No relevant jobs yet. They appear when collected jobs are evaluated for your intent.
        </p>
      )}
      {data && data.rows.length > 0 && (
        <div className="relative overflow-x-auto">
          <table aria-label={title} className="w-full text-sm">
            <thead className="text-xs text-ink-3">
              <tr>
                <th className="px-4 py-2 text-left font-medium">Term</th>
                <th className="px-2 py-2 text-right font-medium">Open</th>
                <th className="px-2 py-2 text-right font-medium">Share</th>
                <th className="px-2 py-2 text-right font-medium">Change</th>
                <th className="px-4 py-2 text-right font-medium">
                  <span className="sr-only">Trend</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((row) => (
                <tr key={row.term_key} className="border-t border-line">
                  <th scope="row" className="px-4 py-2 text-left font-medium">
                    {row.label}
                  </th>
                  <td className="px-2 py-2 text-right tabular-nums">{row.open_now}</td>
                  <td className="px-2 py-2 text-right tabular-nums">{percent(row.share_now)}</td>
                  <td className="px-2 py-2 text-right tabular-nums text-ink-2">
                    {formatPoints(row.share_change)}
                  </td>
                  <td className="px-4 py-2 text-right">
                    <Sparkline label={row.label} values={row.series.map((p) => p.share)} />
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
