import type { ReactNode } from 'react'
import { useId } from 'react'

interface Props {
  title: string
  hint?: string
  /** Controls shown on the right of the heading. */
  actions?: ReactNode
  children: ReactNode
}

/** A titled section card; the heading labels the region for assistive technology. */
export function Card({ title, hint, actions, children }: Props) {
  const id = useId()
  return (
    <section aria-labelledby={id} className="rounded-lg border border-line bg-surface p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 id={id} className="text-sm font-semibold">
            {title}
          </h2>
          {hint && <p className="mt-0.5 text-xs text-ink-3">{hint}</p>}
        </div>
        {actions}
      </div>
      <div className="mt-3">{children}</div>
    </section>
  )
}
