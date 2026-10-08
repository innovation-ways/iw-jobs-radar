import type { Dossier } from './queries'

type Week = Dossier['hiring'][number]

/**
 * Weekly new offers as small bars. The picture has a text alternative with the same numbers, and
 * a visually hidden table lists every week for assistive technology.
 */
export function HiringChart({ weeks }: { weeks: Week[] }) {
  const max = Math.max(1, ...weeks.map((w) => w.new_offers))
  const summary = weeks.map((w) => `${w.week_start}: ${w.new_offers}`).join(', ')
  const width = 12 * weeks.length
  return (
    <div>
      <svg
        role="img"
        aria-label={`Weekly new offers over the last ${weeks.length} weeks. ${summary}`}
        viewBox={`0 0 ${width} 40`}
        className="h-20 w-full max-w-md text-brand"
        preserveAspectRatio="none"
      >
        {weeks.map((w, i) => {
          const height = (w.new_offers / max) * 36
          return (
            <rect
              key={w.week_start}
              x={i * 12 + 2}
              y={38 - height}
              width={8}
              height={Math.max(height, w.new_offers ? 1 : 0)}
              fill="currentColor"
            />
          )
        })}
        <line x1="0" y1="38.5" x2={width} y2="38.5" stroke="currentColor" strokeOpacity="0.3" />
      </svg>
      <table className="sr-only">
        <caption>Offers per week</caption>
        <thead>
          <tr>
            <th>Week starting</th>
            <th>New</th>
            <th>Open</th>
          </tr>
        </thead>
        <tbody>
          {weeks.map((w) => (
            <tr key={w.week_start}>
              <td>{w.week_start}</td>
              <td>{w.new_offers}</td>
              <td>{w.open_offers}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-xs text-ink-3">
        New offers per week · most recent week on the right · highest week: {max}
      </p>
    </div>
  )
}
