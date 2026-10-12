import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { formatDateTime } from '@/lib/format'

/** One cited statement of the deep company analysis (ADR-054). */
export interface AnalysisStatement {
  topic: string
  text: string
  quote: string
  page_url: string
}

/** The stored value of the `ai_dossier` fact. */
export interface AnalysisValue {
  /** Two or three sentences: what the company does and how it makes money (newer analyses). */
  overview?: string
  company_type?: string
  remote_policy?: string
  statements: AnalysisStatement[]
  open_questions: string[]
  pages: string[]
  dropped: number
}

const TOPIC_LABELS: Record<string, string> = {
  offering: 'What it offers',
  customers: 'Customers',
  locations: 'Where it operates',
  size_and_stage: 'Size and stage',
  financials: 'Funding and revenue',
  technology: 'Technology',
  remote_policy: 'Remote or hybrid policy',
  culture: 'Culture and benefits',
  risks: 'Risks',
  other: 'Other',
  // Topics of analyses written before the profile format; kept so they still display.
  product: 'Product',
  business_model: 'Business model',
  engineering_culture: 'Engineering culture',
  portugal_presence: 'Presence in Portugal',
}
const COMPANY_TYPE_LABELS: Record<string, string> = {
  product: 'Sells a product',
  consulting_outsourcing: 'Consulting / outsourcing',
  staffing_recruitment: 'Staffing / recruitment',
  agency: 'Agency',
  marketplace_platform: 'Marketplace / platform',
  other: 'Other type',
}
const REMOTE_LABELS: Record<string, string> = {
  remote: 'Remote',
  hybrid: 'Hybrid',
  on_site: 'On site',
}
// Topics the owner cares about most come first.
const TOPIC_ORDER = Object.keys(TOPIC_LABELS)

/** Narrow the untyped fact value; a malformed stored value must never break the page. */
function asAnalysis(value: unknown): AnalysisValue | null {
  if (value === null || typeof value !== 'object') return null
  const v = value as Partial<AnalysisValue>
  if (!Array.isArray(v.statements)) return null
  return {
    overview: typeof v.overview === 'string' ? v.overview : undefined,
    company_type: typeof v.company_type === 'string' ? v.company_type : undefined,
    remote_policy: typeof v.remote_policy === 'string' ? v.remote_policy : undefined,
    statements: v.statements,
    open_questions: Array.isArray(v.open_questions) ? v.open_questions : [],
    pages: Array.isArray(v.pages) ? v.pages : [],
    dropped: typeof v.dropped === 'number' ? v.dropped : 0,
  }
}

/** Readable form of a page address: host and path, without the scheme. */
function shortUrl(url: string): string {
  return url.replace(/^https?:\/\/(www\.)?/, '').replace(/\/$/, '')
}

/**
 * The deep analysis of a company: the overview with the kind of company and the work model, then
 * statements grouped by topic. Each statement keeps the quote it rests on and a link to the page
 * behind a "Source" disclosure. Always labelled AI inference. Props: the stored fact value, the model that
 * wrote it and when.
 */
export function AnalysisCard({
  value,
  model,
  retrievedAt,
}: {
  value: unknown
  model: string
  retrievedAt: string
}) {
  const analysis = asAnalysis(value)
  if (!analysis) return <p className="text-sm text-ink-2">The analysis could not be shown.</p>
  // "unknown" and "not stated" are the absence of an answer, not something to show as a fact.
  const type = analysis.company_type ? COMPANY_TYPE_LABELS[analysis.company_type] : undefined
  const remote = analysis.remote_policy ? REMOTE_LABELS[analysis.remote_policy] : undefined
  const topics = TOPIC_ORDER.filter((t) => analysis.statements.some((s) => s.topic === t))
  return (
    <div className="flex flex-col gap-3 text-sm">
      <div className="flex flex-wrap items-center gap-1.5 text-xs text-ink-3">
        <span className="rounded bg-caution/20 px-1.5 py-px font-medium text-ink">
          AI inference
        </span>
        <span>{model}</span>
        <span>{formatDateTime(retrievedAt)}</span>
        <span>{analysis.pages.length} pages read</span>
      </div>
      {analysis.overview && <p>{analysis.overview}</p>}
      {(type || remote) && (
        <ul className="flex flex-wrap gap-1.5 text-xs">
          {type && <li className="rounded bg-surface-2 px-2 py-0.5 text-ink-2">{type}</li>}
          {remote && (
            <li className="rounded bg-surface-2 px-2 py-0.5 text-ink-2">{remote} work model</li>
          )}
        </ul>
      )}
      {topics.map((topic) => (
        <div key={topic}>
          <h4 className="text-xs font-semibold uppercase tracking-wide text-ink-3">
            {TOPIC_LABELS[topic]}
          </h4>
          <ul className="mt-1 flex flex-col gap-2">
            {analysis.statements
              .filter((s) => s.topic === topic)
              .map((s) => (
                <li key={`${s.topic}-${s.text}`}>
                  <div>{s.text}</div>
                  <details className="text-xs text-ink-3">
                    <summary className="cursor-pointer">Source</summary>“{s.quote}” ·{' '}
                    <a
                      className="underline"
                      href={s.page_url}
                      target="_blank"
                      rel="noreferrer noopener"
                    >
                      {shortUrl(s.page_url)}
                    </a>
                  </details>
                </li>
              ))}
          </ul>
        </div>
      ))}
      {analysis.open_questions.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold uppercase tracking-wide text-ink-3">
            Not answered by the pages
          </h4>
          <ul className="mt-1 list-disc pl-5 text-ink-2">
            {analysis.open_questions.map((q) => (
              <li key={q}>{q}</li>
            ))}
          </ul>
        </div>
      )}
      {analysis.dropped > 0 && (
        <p className="text-xs text-ink-3">
          {analysis.dropped} statements without a matching quote were dropped.
        </p>
      )}
    </div>
  )
}

/**
 * Field to record the company's own website. Props: whether a request is running and the submit
 * handler, which receives the text as typed (the server normalises and validates it).
 */
export function WebsiteForm({
  pending,
  onSubmit,
}: {
  pending: boolean
  onSubmit: (url: string) => void
}) {
  const [url, setUrl] = useState('')
  return (
    <form
      className="flex flex-wrap items-center gap-2"
      onSubmit={(event) => {
        event.preventDefault()
        if (url.trim()) onSubmit(url.trim())
      }}
    >
      <label className="sr-only" htmlFor="company-website">
        Company website
      </label>
      <input
        id="company-website"
        className="h-8 w-64 rounded-md border border-line bg-surface px-2 text-sm"
        placeholder="https://example.com"
        value={url}
        onChange={(event) => setUrl(event.target.value)}
      />
      <Button size="sm" type="submit" disabled={pending || !url.trim()}>
        Save website
      </Button>
    </form>
  )
}
