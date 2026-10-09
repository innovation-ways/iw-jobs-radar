import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { PATH_LABELS, summarise } from './format'
import type { Decision, ProposalItem } from './queries'

type Kind = Decision['decision']
const KINDS: { value: Kind; label: string }[] = [
  { value: 'accept', label: 'Accept' },
  { value: 'edit', label: 'Edit' },
  { value: 'reject', label: 'Reject' },
  { value: 'defer', label: 'Defer' },
]
const field = 'rounded-md border border-line-strong bg-surface px-2 py-1 text-sm'

/** Fields with a closed set of values (mirrors the backend schemas), edited with a dropdown. */
const OPTIONS: Record<string, Record<string, readonly string[]>> = {
  skills: {
    level: ['beginner', 'intermediate', 'advanced', 'expert'],
    kind: ['technology', 'domain_knowledge', 'method'],
  },
  languages: { level: ['A1', 'A2', 'B1', 'B2', 'C1', 'C2', 'native'] },
}

/** Inputs for each key of an object value (or one input for a plain value). */
function ValueEditor({
  value,
  onChange,
  label,
  path,
}: {
  value: unknown
  onChange: (value: unknown) => void
  label: string
  path: string
}) {
  if (value === null || typeof value !== 'object') {
    return (
      <input
        aria-label={`${label}: value`}
        className={field}
        value={String(value ?? '')}
        onChange={(e) =>
          onChange(typeof value === 'number' ? Number(e.target.value) : e.target.value)
        }
      />
    )
  }
  const entries = Object.entries(value as Record<string, unknown>)
  return (
    <div className="flex flex-wrap gap-2">
      {entries.map(([key, current]) => {
        const options = OPTIONS[path]?.[key]
        return (
          <label key={key} className="flex flex-col gap-0.5 text-xs text-ink-2">
            {key}
            {options ? (
              <select
                aria-label={`${label}: ${key}`}
                className={field}
                value={String(current ?? '')}
                onChange={(e) =>
                  onChange({ ...(value as Record<string, unknown>), [key]: e.target.value })
                }
              >
                {/* Keep an unexpected current value selectable instead of silently changing it. */}
                {!options.includes(String(current)) && <option>{String(current ?? '')}</option>}
                {options.map((option) => (
                  <option key={option}>{option}</option>
                ))}
              </select>
            ) : (
              <input
                aria-label={`${label}: ${key}`}
                className={field}
                value={current === null ? '' : String(current)}
                onChange={(e) => {
                  const raw = e.target.value
                  const next = typeof current === 'number' ? Number(raw) : raw === '' ? null : raw
                  onChange({ ...(value as Record<string, unknown>), [key]: next })
                }}
              />
            )}
          </label>
        )
      })}
    </div>
  )
}

interface Props {
  items: ProposalItem[]
  applying: boolean
  revisionNumber: number | null
  onApply: (decisions: Decision[]) => void
}

/**
 * The proposals of one CV, one row per proposed fact with the quote that supports it. Nothing
 * becomes a profile fact until it is accepted or edited and the review is applied.
 */
export function ProposalReview({ items, applying, revisionNumber, onApply }: Props) {
  const open = items.filter((i) => i.review_status === 'pending' || i.review_status === 'deferred')
  const [choice, setChoice] = useState<Record<number, Kind>>({})
  const [edits, setEdits] = useState<Record<number, unknown>>({})
  const decided = open.filter((i) => choice[i.proposal_item_id]).length

  /** Mark every item that has no decision yet as accepted; explicit choices are kept. */
  function acceptAll() {
    const next = { ...choice }
    for (const i of open) next[i.proposal_item_id] ??= 'accept'
    setChoice(next)
  }

  function apply() {
    const decisions: Decision[] = open
      .filter((i) => choice[i.proposal_item_id])
      .map((i) => {
        const decision = choice[i.proposal_item_id]
        return decision === 'edit'
          ? {
              proposal_item_id: i.proposal_item_id,
              decision,
              value: edits[i.proposal_item_id] ?? i.value,
            }
          : { proposal_item_id: i.proposal_item_id, decision }
      })
    onApply(decisions)
  }

  return (
    <section aria-labelledby="proposals" className="rounded-lg border border-line bg-surface">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-3">
        <div>
          <h3 id="proposals" className="text-sm font-semibold">
            Proposals from your CV
          </h3>
          <p className="text-xs text-ink-3">
            Nothing becomes part of your profile until you accept or edit it.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="rounded bg-surface-2 px-2 py-0.5 text-xs">
            {decided} of {open.length} decided
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={decided === open.length || applying}
            onClick={acceptAll}
          >
            Accept all undecided
          </Button>
        </div>
      </div>
      <ul>
        {open.map((item) => {
          const id = item.proposal_item_id
          const label = `${PATH_LABELS[item.path] ?? item.path}: ${summarise(item.path, item.value)}`
          return (
            <li key={id} className="border-t border-line px-4 py-3 first:border-t-0">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="text-xs text-ink-3">{PATH_LABELS[item.path] ?? item.path}</div>
                  <div className="font-medium">{summarise(item.path, item.value)}</div>
                  {item.source_excerpt ? (
                    <blockquote className="mt-1 border-l-[3px] border-brand pl-2 text-[13px] text-ink-2">
                      “{item.source_excerpt}”
                    </blockquote>
                  ) : (
                    <p className="mt-1 text-xs text-ink-3">No supporting quote was found.</p>
                  )}
                </div>
                <div className="text-right text-xs text-ink-3">
                  {item.confidence !== null && (
                    <div>Confidence {Math.round(Number(item.confidence) * 100)}%</div>
                  )}
                  {item.review_status === 'deferred' && <div>Deferred earlier</div>}
                </div>
              </div>
              <div role="radiogroup" aria-label={label} className="mt-2 flex flex-wrap gap-1.5">
                {KINDS.map((kind) => (
                  <label
                    key={kind.value}
                    // `relative` anchors the visually hidden radio: without a positioned ancestor it
                    // is placed outside the scrolling <main>, and focusing it scrolls the whole
                    // document, which cuts the page off halfway.
                    className={`relative cursor-pointer rounded-md border px-2.5 py-1 text-sm ${
                      choice[id] === kind.value
                        ? 'border-brand bg-brand-soft text-brand-text'
                        : 'border-line-strong'
                    }`}
                  >
                    <input
                      type="radio"
                      className="sr-only"
                      name={`decision-${id}`}
                      checked={choice[id] === kind.value}
                      onChange={() => setChoice({ ...choice, [id]: kind.value })}
                    />
                    {kind.label}
                  </label>
                ))}
              </div>
              {choice[id] === 'edit' && (
                <div className="mt-2">
                  <ValueEditor
                    label={label}
                    path={item.path}
                    value={edits[id] ?? item.value}
                    onChange={(value) => setEdits({ ...edits, [id]: value })}
                  />
                </div>
              )}
            </li>
          )
        })}
      </ul>
      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line px-4 py-3">
        <span className="text-xs text-ink-3">
          Rejected and deferred items are kept for audit but never enter your profile.
        </span>
        <Button disabled={decided === 0 || applying} onClick={apply}>
          Apply review → revision {(revisionNumber ?? 0) + 1}
        </Button>
      </div>
    </section>
  )
}
