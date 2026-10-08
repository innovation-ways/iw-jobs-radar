import { cn } from '@/lib/utils'
import type { IntentDefinition, TaxonomyRead } from '@/features/profile/queries'

export type StanceEntry = IntentDefinition['stances']['role_families'][number]
type Stance = StanceEntry['stance']
type Term = TaxonomyRead['groups'][number]['terms'][number]

const OPTIONS: { value: Stance | 'none'; label: string }[] = [
  { value: 'preferred', label: 'Preferred' },
  { value: 'acceptable', label: 'OK' },
  { value: 'rejected', label: 'Reject' },
]

interface Props {
  /** Name of the whole group, for assistive technology and the warning. */
  label: string
  terms: Term[]
  value: StanceEntry[]
  onChange: (value: StanceEntry[]) => void
  /** Open groups (role families, sectors) allow an option to have no opinion (not listed). */
  allowNoOpinion?: boolean
}

/**
 * Preferred / OK / Reject for every option of a vocabulary (ADR-026). Reject is a hard gate.
 * In closed groups every option has a stance; in open groups an option may be left unlisted.
 * Each choice is a real radio input, so it works with the keyboard and screen readers, and the
 * selected state is shown by text styling and not by colour alone.
 */
export function StanceGroup({ label, terms, value, onChange, allowNoOpinion = false }: Props) {
  const stanceOf = (key: string): Stance | 'none' =>
    value.find((entry) => entry.key === key)?.stance ?? (allowNoOpinion ? 'none' : 'acceptable')

  function choose(key: string, stance: Stance | 'none') {
    const others = value.filter((entry) => entry.key !== key)
    if (stance === 'none') return onChange(others)
    // Keep the original order of the vocabulary so saved revisions compare cleanly.
    const next = [...others, { key, stance }]
    onChange(terms.flatMap((term) => next.filter((entry) => entry.key === term.term_key)))
  }

  const options = allowNoOpinion
    ? [...OPTIONS, { value: 'none' as const, label: 'No opinion' }]
    : OPTIONS
  const allRejected = value.length > 0 && value.every((entry) => entry.stance === 'rejected')
  const empty = !allowNoOpinion && value.length === 0

  return (
    <div>
      <ul className="divide-y divide-line">
        {terms.map((term) => {
          const current = stanceOf(term.term_key)
          return (
            <li
              key={term.term_key}
              className="flex flex-wrap items-center justify-between gap-2 py-1.5"
            >
              <span>{term.label}</span>
              <div
                role="radiogroup"
                aria-label={term.label}
                className="inline-flex rounded-md border border-line-strong"
              >
                {options.map((option) => (
                  <label
                    key={option.value}
                    className={cn(
                      'cursor-pointer border-r border-line-strong px-2.5 py-1 text-xs font-medium last:border-r-0 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-brand',
                      current === option.value
                        ? 'bg-brand-soft text-brand-text'
                        : 'text-ink-2 hover:bg-surface-2',
                      current === option.value &&
                        option.value === 'rejected' &&
                        'bg-bad-bg text-bad',
                    )}
                  >
                    <input
                      type="radio"
                      className="sr-only"
                      name={`${label}-${term.term_key}`}
                      value={option.value}
                      checked={current === option.value}
                      onChange={() => choose(term.term_key, option.value)}
                    />
                    {option.label}
                  </label>
                ))}
              </div>
            </li>
          )
        })}
      </ul>
      {(allRejected || empty) && (
        <p role="alert" className="mt-2 text-sm text-bad">
          {label}: at least one option must not be rejected, otherwise nothing could ever match.
        </p>
      )}
    </div>
  )
}
