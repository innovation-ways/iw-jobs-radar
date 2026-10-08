/**
 * A tiny line of the weekly values. It is a picture of the shape only: the text alternative lists
 * every value, and the table next to it shows the latest number.
 */
export function Sparkline({ label, values }: { label: string; values: (number | null)[] }) {
  const known = values.filter((v): v is number => v !== null)
  const min = Math.min(...known, 0)
  const max = Math.max(...known, 0.0001)
  const width = 80
  const height = 24
  const points = values
    .map((v, i) =>
      v === null
        ? null
        : `${(i / Math.max(values.length - 1, 1)) * width},${height - 2 - ((v - min) / (max - min || 1)) * (height - 4)}`,
    )
    .filter(Boolean)
    .join(' ')
  const text = values.map((v) => (v === null ? 'n/a' : `${Math.round(v * 100)}%`)).join(', ')
  return (
    <svg
      role="img"
      aria-label={`${label}: weekly share ${text}`}
      viewBox={`0 0 ${width} ${height}`}
      className="h-6 w-20 text-brand"
    >
      <polyline points={points} fill="none" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  )
}
