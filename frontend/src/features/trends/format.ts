/** A share such as 0.6 as "60%" (an en dash when unknown). */
export function percent(value: number | null): string {
  return value === null ? '–' : `${Math.round(value * 100)}%`
}

/** A change in share as signed percentage points: "+20 pts", "−10 pts", "no change". */
export function formatPoints(change: number | null): string {
  if (change === null) return 'n/a'
  const points = Math.round(change * 100)
  if (points === 0) return 'no change'
  return `${points > 0 ? '+' : '−'}${Math.abs(points)} pts`
}
