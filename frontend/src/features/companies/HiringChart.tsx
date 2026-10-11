import type { Dossier } from './queries'

type Week = Dossier['hiring'][number]

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** "28 Sep" for a `YYYY-MM-DD` week start; spelled out so it does not depend on the locale data. */
function shortDate(weekStart: string): string {
  const [, month, day] = weekStart.split('-').map(Number)
  return `${day} ${MONTHS[month - 1]}`
}

const plural = (n: number, noun: string) => `${n} ${noun}${n === 1 ? '' : 's'}`

/**
 * Weekly new offers as labelled bars: each bar is one week, its height is the number of offers
 * first seen that week. A vertical axis gives the busiest week and zero, a horizontal axis the
 * first and last week. Hovering or focusing a bar shows a tooltip in words (week, new offers, open
 * offers at the end of that week); the same sentence is the bar's accessible name, so the chart
 * does not rely on hover or colour.
 */
export function HiringChart({ weeks }: { weeks: Week[] }) {
  const max = Math.max(...weeks.map((w) => w.new_offers), 0)
  if (weeks.length === 0 || max === 0) {
    return (
      <p className="text-sm text-ink-2">
        No new offers in these {weeks.length} weeks, so there is nothing to chart.
      </p>
    )
  }
  const first = weeks[0]
  const last = weeks[weeks.length - 1]
  return (
    <div>
      <p className="mb-2 text-xs text-ink-2">
        Each bar is one week; its height is how many offers from this company were first seen that
        week. Hover or focus a bar for the details.
      </p>
      <div className="flex gap-2">
        <div
          data-testid="hiring-y-axis"
          className="flex h-24 flex-col justify-between text-right text-[11px] text-ink-3 tabular-nums"
        >
          <span>{max}</span>
          <span>0</span>
        </div>
        <div className="min-w-0 flex-1">
          <div
            role="group"
            aria-label={`New offers per week, last ${weeks.length} weeks`}
            className="flex h-24 items-end gap-1 border-b border-l border-line-strong"
          >
            {weeks.map((w, i) => {
              const week = `Week of ${shortDate(w.week_start)}`
              const news = plural(w.new_offers, 'new offer')
              const open = `${w.open_offers} open at the end of the week`
              // Keep the tooltip inside the chart: the outer bars anchor it to their own edge.
              const anchor =
                i < 2 ? 'left-0' : i > weeks.length - 3 ? 'right-0' : 'left-1/2 -translate-x-1/2'
              return (
                <div
                  key={w.week_start}
                  role="img"
                  tabIndex={0}
                  aria-label={`${week}: ${news}, ${open}`}
                  className="group relative flex h-full flex-1 items-end rounded-sm outline-offset-2 hover:bg-surface-2 focus-visible:bg-surface-2"
                >
                  <div
                    data-testid="hiring-bar"
                    style={{ height: `${(w.new_offers / max) * 100}%` }}
                    // A week with offers always shows at least a sliver, so it is not mistaken for 0.
                    className="min-h-[2px] w-full rounded-t-sm bg-brand data-[empty=true]:min-h-0"
                    data-empty={w.new_offers === 0}
                  />
                  <div
                    aria-hidden="true"
                    className={`pointer-events-none absolute bottom-full z-20 mb-1 hidden w-max rounded-md border border-line-strong bg-surface px-2 py-1 text-xs shadow-md group-focus-visible:block group-hover:block ${anchor}`}
                  >
                    <div className="font-semibold">{week}</div>
                    <div>{news}</div>
                    <div className="text-ink-2">{open}</div>
                  </div>
                </div>
              )
            })}
          </div>
          <div className="mt-1 flex justify-between text-[11px] text-ink-3 tabular-nums">
            <span>{shortDate(first.week_start)}</span>
            <span>weeks, oldest to newest</span>
            <span>{shortDate(last.week_start)}</span>
          </div>
        </div>
      </div>
    </div>
  )
}
