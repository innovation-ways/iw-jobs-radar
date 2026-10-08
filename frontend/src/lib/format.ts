const dateTime = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' })

/** A timestamp in the viewer's locale and time zone, for example "8 Oct 2026, 08:30". */
export function formatDateTime(iso: string): string {
  return dateTime.format(new Date(iso))
}

const MINUTE = 60_000
const HOUR = 60 * MINUTE
const DAY = 24 * HOUR

/** A short age such as "2h", "3d" or "5w" for a past timestamp ("just now" under a minute). */
export function formatAge(iso: string, now: Date = new Date()): string {
  const elapsed = Math.max(0, now.getTime() - new Date(iso).getTime())
  if (elapsed < MINUTE) return 'just now'
  if (elapsed < HOUR) return `${Math.floor(elapsed / MINUTE)}m`
  if (elapsed < DAY) return `${Math.floor(elapsed / HOUR)}h`
  const days = Math.floor(elapsed / DAY)
  if (days < 21) return `${days}d`
  if (days < 60) return `${Math.floor(days / 7)}w`
  if (days < 365) return `${Math.floor(days / 30)}mo`
  return `${Math.floor(days / 365)}y`
}
