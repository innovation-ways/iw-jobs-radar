import { useState } from 'react'
import { TrendCard } from '@/features/trends/TrendCard'
import { useTrends } from '@/features/trends/queries'
import { formatDateTime } from '@/lib/format'

const PERIODS = [
  { key: '4w', label: '4 weeks', weeks: 4 },
  { key: '12w', label: '12 weeks', weeks: 12 },
  { key: '6m', label: '6 months', weeks: 26 },
] as const

const CARDS = [
  { kind: 'skill', title: 'Technologies' },
  { kind: 'role_family', title: 'Role families' },
  { kind: 'sector', title: 'Sectors' },
  { kind: 'work_arrangement', title: 'Work arrangements' },
  { kind: 'seniority_level', title: 'Seniority' },
  { kind: 'engagement_type', title: 'Engagement types' },
] as const

const day = (iso: string) => formatDateTime(`${iso}T00:00:00Z`).split(',')[0]

/**
 * Market trends: how demand for terms changes among the jobs that are relevant to the search
 * intent. Shares are shown next to counts (adding sources raises counts), weeks where the intent
 * or the sources changed are called out, and only the history that exists can be selected.
 */
export function Trends() {
  const [weeks, setWeeks] = useState(12)
  const base = useTrends('skill', weeks)
  const report = base.data

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-4 px-6 py-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Market trends</h2>
          <p className="text-sm text-ink-2">
            Only jobs relevant to your intent
            {report ? ` (fit of ${report.relevance_min_score} or higher, not ruled out)` : ''}.
          </p>
        </div>
        <span role="group" aria-label="Period" className="flex gap-1">
          {PERIODS.map((period) => {
            const info = report?.periods.find((p) => p.key === period.key)
            const locked = info ? !info.available : period.weeks > 4
            return (
              <button
                key={period.key}
                type="button"
                aria-pressed={weeks === period.weeks}
                disabled={locked}
                title={locked ? 'Unlocks automatically once enough data exists' : undefined}
                onClick={() => setWeeks(period.weeks)}
                className={`rounded-md border px-3 py-1.5 text-sm ${weeks === period.weeks ? 'border-brand bg-brand-soft text-brand-text' : 'border-line-strong'} disabled:cursor-not-allowed disabled:opacity-50`}
              >
                {period.label}
              </button>
            )
          })}
        </span>
      </div>

      {base.isError ? (
        <p
          role="alert"
          className="rounded-md border border-line bg-surface px-4 py-3 text-sm text-ink-2"
        >
          {base.error.message}
        </p>
      ) : (
        <>
          {report && (
            <div className="rounded-md bg-brand-soft px-3.5 py-2 text-sm text-brand-text">
              {report.first_week ? (
                <>
                  History available: <strong>{report.available_weeks} weeks</strong> (from{' '}
                  {day(report.first_week)}). Longer periods unlock automatically as data
                  accumulates.
                </>
              ) : (
                'No history yet. Trends appear after jobs are collected and evaluated.'
              )}
            </div>
          )}
          {report?.intent_revision_changes.map((week) => (
            <p key={`i-${week}`} className="text-sm text-ink-2">
              Your search intent changed in the week of {day(week)}; weeks before it were counted
              with the earlier version, so compare shares with care.
            </p>
          ))}
          {report?.source_set_changes.map((week) => (
            <p key={`s-${week}`} className="text-sm text-ink-2">
              Your sources changed in the week of {day(week)}; counts before and after are not
              directly comparable, so look at shares.
            </p>
          ))}
          <div className="grid items-start gap-4 md:grid-cols-2">
            {CARDS.map((card) => (
              <TrendCard key={card.kind} kind={card.kind} title={card.title} weeks={weeks} />
            ))}
          </div>
        </>
      )}
    </div>
  )
}
