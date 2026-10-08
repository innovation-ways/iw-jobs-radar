const dateTime = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' })

/** A timestamp in the viewer's locale and time zone, for example "8 Oct 2026, 08:30". */
export function formatDateTime(iso: string): string {
  return dateTime.format(new Date(iso))
}
