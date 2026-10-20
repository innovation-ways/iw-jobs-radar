import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import {
  DEFAULT_WEIGHTS,
  DIMENSIONS,
  MAX_WEIGHT,
  OPTIONAL_DIMENSIONS,
  effectiveShares,
  hasAnyWeight,
  scoreWith,
  type Dimension,
  type WeightKey,
  type Weights,
} from './weights'

/** Strengths of the worked example in document 13, section 7 (compensation unknown). */
const EXAMPLE_STRENGTHS: Record<WeightKey, number | null> = {
  role_responsibilities: 1,
  skills_technology: 0.8,
  work_arrangement_location: 1,
  engagement_terms: 1,
  compensation: null,
  seniority_experience: 1,
  domain_sector: 0.5,
  company_profile: 1,
  benefits_flexibility: null,
  qualifications: null,
  career_direction: null,
  schedule_travel: null,
}

interface Props {
  value: Weights
  onChange: (value: Weights) => void
}

function Row({
  dimension,
  value,
  share,
  onChange,
}: {
  dimension: Dimension
  value: Weights
  share: number | null
  onChange: (value: Weights) => void
}) {
  const weight = value[dimension.key]
  const excluded = weight === 0
  const modified = weight !== DEFAULT_WEIGHTS[dimension.key]
  const tooltipId = `tip-${dimension.key}`
  return (
    <div
      data-dimension={dimension.key}
      data-excluded={excluded}
      className={cn(
        'grid grid-cols-[minmax(0,1.2fr)_minmax(0,1.6fr)_auto] items-center gap-3 py-2',
        excluded && 'opacity-55',
      )}
    >
      <span className="group relative">
        <span
          tabIndex={0}
          aria-describedby={tooltipId}
          className="cursor-help font-medium underline decoration-dotted underline-offset-4"
        >
          {dimension.label}
        </span>
        <span
          id={tooltipId}
          role="tooltip"
          aria-label={`${dimension.label}: description`}
          className="pointer-events-none absolute left-0 top-full z-20 mt-1 hidden w-72 rounded-md border border-line bg-surface p-3 text-xs font-normal text-ink-2 shadow-lg group-focus-within:block group-hover:block"
        >
          {dimension.description}
        </span>
      </span>
      <div>
        <input
          type="range"
          min={0}
          max={MAX_WEIGHT}
          step={1}
          value={weight}
          aria-label={`${dimension.label} weight`}
          onChange={(event) => onChange({ ...value, [dimension.key]: Number(event.target.value) })}
          className="w-full accent-[var(--accent)]"
        />
        <div className="text-xs text-ink-3">
          default {DEFAULT_WEIGHTS[dimension.key]}
          {modified && (
            <>
              {' · '}
              <button
                type="button"
                className="underline"
                aria-label={`Reset ${dimension.label} to its default`}
                onClick={() =>
                  onChange({ ...value, [dimension.key]: DEFAULT_WEIGHTS[dimension.key] })
                }
              >
                reset
              </button>
            </>
          )}
        </div>
      </div>
      <div className="min-w-28 text-right">
        <b className={cn('tabular-nums', modified && 'text-brand-text')}>{weight}</b>
        <div className="text-xs text-ink-3">
          {excluded
            ? 'Excluded from score'
            : share === null
              ? '—'
              : `${Math.round(share)}% of score`}
        </div>
      </div>
    </div>
  )
}

/**
 * Relative weights of the scoring dimensions. A weight of 0 excludes a dimension (shown greyed);
 * the shares always add up to 100. The impact on already scored jobs arrives with evaluation.
 */
export function WeightsPanel({ value, onChange }: Props) {
  const shares = effectiveShares(value)
  const example = scoreWith(EXAMPLE_STRENGTHS, DEFAULT_WEIGHTS)
  const raised = scoreWith(EXAMPLE_STRENGTHS, { ...DEFAULT_WEIGHTS, compensation: 30 })
  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
      <section
        aria-labelledby="weights-title"
        className="rounded-lg border border-line bg-surface p-4"
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 id="weights-title" className="text-sm font-semibold">
              What matters most to you
            </h2>
            <p className="text-xs text-ink-3">
              Weights are relative: the score is always out of 100, so raising one lowers the share
              of the others.
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={() => onChange({ ...DEFAULT_WEIGHTS })}>
            Reset all weights
          </Button>
        </div>
        <div className="mt-2 divide-y divide-line">
          {DIMENSIONS.map((dimension) => (
            <Row
              key={dimension.key}
              dimension={dimension}
              value={value}
              share={shares[dimension.key]}
              onChange={onChange}
            />
          ))}
        </div>
        <h3 className="mt-3 border-t border-line pt-3 text-[11px] font-semibold tracking-wider text-ink-3 uppercase">
          Optional criteria · off by default
        </h3>
        <div className="divide-y divide-line">
          {OPTIONAL_DIMENSIONS.map((dimension) => (
            <Row
              key={dimension.key}
              dimension={dimension}
              value={value}
              share={shares[dimension.key]}
              onChange={onChange}
            />
          ))}
        </div>
        {!hasAnyWeight(value) && (
          <p role="alert" className="mt-2 text-sm text-bad">
            At least one weight must be above 0.
          </p>
        )}
      </section>
      <section
        aria-labelledby="weights-note"
        className="h-fit rounded-lg border border-line bg-surface p-4"
      >
        <h2 id="weights-note" className="text-sm font-semibold">
          How weights work
        </h2>
        <p className="mt-2 rounded-md bg-brand-soft px-3 py-2 text-sm text-brand-text">
          <strong>Changing weights does not change scores that were already calculated.</strong> New
          weights apply to jobs evaluated from now on.
        </p>
        <p className="mt-3 text-sm text-ink-2">
          Example: a job that scores <strong>{example}</strong> with the default weights scores{' '}
          <strong>{raised}</strong> if compensation is raised from 10 to 30 and the posting does not
          state its pay (unknown pay adds nothing, while its weight still counts).
        </p>
        <p className="mt-3 text-xs text-ink-3">
          The effect on your current jobs will be shown here once jobs have been scored.
        </p>
      </section>
    </div>
  )
}
