import { X } from 'lucide-react'
import { useId, useState } from 'react'

interface Props {
  label: string
  values: string[]
  onChange: (values: string[]) => void
  placeholder?: string
  /** Applied to what the owner types before it is checked and stored (for example upper-casing). */
  normalise?: (value: string) => string
  /** Returns a message when the value is not acceptable, or `null`. */
  validate?: (value: string) => string | null
}

/**
 * A list of short values shown as chips with a field to add more (Enter, comma or leaving the
 * field). Duplicates (ignoring case) and blanks are ignored. Each chip has a Remove button.
 */
export function ChipsInput({ label, values, onChange, placeholder, normalise, validate }: Props) {
  const [text, setText] = useState('')
  const [error, setError] = useState<string | null>(null)
  const id = useId()

  function commit(raw: string) {
    const value = (normalise ? normalise(raw.trim()) : raw.trim()).trim()
    if (!value) return setText('')
    const problem = validate?.(value) ?? null
    if (problem) return setError(problem)
    setError(null)
    setText('')
    if (values.some((existing) => existing.toLowerCase() === value.toLowerCase())) return
    onChange([...values, value])
  }

  return (
    <div>
      <label htmlFor={id} className="text-xs text-ink-2">
        {label}
      </label>
      <div className="mt-1 flex flex-wrap items-center gap-1.5">
        {values.map((value) => (
          <span
            key={value}
            className="inline-flex items-center gap-1 rounded-full border border-line-strong bg-surface-2 py-0.5 pr-1 pl-2.5 text-xs"
          >
            {value}
            <button
              type="button"
              aria-label={`Remove ${value}`}
              onClick={() => onChange(values.filter((existing) => existing !== value))}
              className="rounded-full p-0.5 text-ink-3 hover:bg-surface-3 hover:text-ink"
            >
              <X className="size-3" />
            </button>
          </span>
        ))}
        <input
          id={id}
          value={text}
          placeholder={placeholder ?? 'Add…'}
          onChange={(event) => {
            const next = event.target.value
            if (next.endsWith(',')) commit(next.slice(0, -1))
            else setText(next)
          }}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault() // do not submit a surrounding form
              commit(text)
            }
          }}
          onBlur={() => text.trim() && commit(text)}
          className="min-w-32 flex-1 rounded-md border border-line-strong bg-surface px-2 py-1 text-sm"
        />
      </div>
      {error && (
        <p role="alert" className="mt-1 text-xs text-bad">
          {error}
        </p>
      )}
    </div>
  )
}
