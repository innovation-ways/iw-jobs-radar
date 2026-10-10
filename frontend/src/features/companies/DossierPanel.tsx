import { useEffect, useRef } from 'react'
import { Button } from '@/components/ui/button'
import { formatAge, formatDateTime } from '@/lib/format'
import { HiringChart } from './HiringChart'
import { useDossier, useDossierActions, type Dossier } from './queries'

const FACT_LABELS: Record<string, string> = {
  homepage: 'Website',
  description: 'Description',
  industry: 'Industry',
  employee_count: 'Employees',
  headquarters: 'Headquarters',
  founded_year: 'Founded',
  legal_entity: 'Legal entity',
  technologies: 'Technologies',
  stage: 'Stage',
  ai_summary: 'Summary',
}
const HIDDEN = new Set(['homepage'])

/**
 * Public page of a candidate entity, so the owner can compare look-alike candidates.
 * Only Wikidata is linked today; other datasets return null (no link shown).
 */
function candidateUrl(sourceName: string, externalId: string): string | null {
  // The identifier is encoded because it comes from an external dataset.
  return sourceName === 'wikidata'
    ? `https://www.wikidata.org/wiki/${encodeURIComponent(externalId)}`
    : null
}

function factText(value: unknown): string {
  if (Array.isArray(value)) return value.join(', ')
  if (value !== null && typeof value === 'object') {
    const o = value as Record<string, unknown>
    return [o.name, o.lei, o.country, o.status].filter(Boolean).join(' · ')
  }
  return String(value)
}

function Fact({ fact }: { fact: Dossier['facts'][number] }) {
  const ai = fact.origin === 'ai_inference'
  return (
    <li className="grid grid-cols-[130px_1fr] gap-3 border-t border-line py-2 first:border-t-0">
      <span className="text-xs text-ink-3">{FACT_LABELS[fact.fact_key] ?? fact.fact_key}</span>
      <div>
        <div>{factText(fact.value)}</div>
        <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-ink-3">
          <span
            className={`rounded px-1.5 py-px font-medium ${ai ? 'bg-caution/20 text-ink' : 'bg-surface-2 text-ink-2'}`}
          >
            {ai ? 'AI inference' : fact.label}
          </span>
          {fact.source_url ? (
            <a
              className="underline"
              href={fact.source_url}
              target="_blank"
              rel="noreferrer noopener"
            >
              {fact.source_name}
            </a>
          ) : (
            <span>{fact.source_name}</span>
          )}
          {fact.licence && (
            <span>
              {fact.source_name} · {fact.licence}
            </span>
          )}
          <span>{formatDateTime(fact.retrieved_at)}</span>
        </div>
        {fact.fact_key === 'description' && fact.licence?.startsWith('CC-BY-SA') && (
          <p className="mt-0.5 text-xs text-ink-3">
            Text from Wikipedia, available under CC BY-SA 4.0.
          </p>
        )}
      </div>
    </li>
  )
}

/**
 * A company dossier: homepage and sourced facts (each labelled Source or AI inference), pending
 * entities to confirm, offers with their fit, and the hiring activity. A dossier that was never
 * looked up (or is older than 30 days) is refreshed once, automatically, when it is opened.
 */
export function DossierPanel({ companyId }: { companyId: number }) {
  const { data, isPending, isError } = useDossier(companyId)
  const { enrich, summarise, decide } = useDossierActions(companyId)
  const attempted = useRef(new Set<number>())

  useEffect(() => {
    if (data?.stale && !attempted.current.has(companyId)) {
      attempted.current.add(companyId)
      enrich.mutate()
    }
  }, [data?.stale, companyId, enrich])

  if (isPending) return <p className="p-6 text-ink-3">Loading…</p>
  if (isError)
    return (
      <p role="alert" className="p-6 text-bad">
        Could not load this company.
      </p>
    )
  const failure = [enrich, summarise, decide].find((m) => m.isError)?.error
  const host = data.homepage_url ? new URL(data.homepage_url).hostname.replace(/^www\./, '') : null

  return (
    <section aria-label={data.name} className="flex flex-col gap-4 p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">{data.name}</h2>
          <p className="mt-1 text-sm text-ink-2">
            {data.homepage_url ? (
              <a
                className="underline"
                href={data.homepage_url}
                target="_blank"
                rel="noreferrer noopener"
              >
                {host}
              </a>
            ) : (
              'Website not known yet'
            )}
            {data.enriched_at && (
              <span className="ml-2 text-ink-3">checked {formatAge(data.enriched_at)} ago</span>
            )}
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            size="sm"
            variant="outline"
            disabled={enrich.isPending}
            onClick={() => enrich.mutate()}
          >
            Update from public sources
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={summarise.isPending}
            onClick={() => summarise.mutate()}
          >
            Write AI summary
          </Button>
        </div>
      </div>
      {enrich.isPending && (
        <p role="status" className="text-sm text-ink-3">
          Looking up public sources…
        </p>
      )}
      {failure && (
        <p role="alert" className="rounded-md bg-bad-bg px-3 py-2 text-sm text-bad">
          {failure.message}
        </p>
      )}
      {data.warnings.length > 0 && (
        <p className="text-xs text-ink-3">
          Some sources could not be read: {data.warnings.join('; ')}
        </p>
      )}

      {data.candidates.length > 0 && (
        <section
          aria-labelledby="candidates"
          className="rounded-lg border border-caution/50 bg-surface-2 p-4"
        >
          <h3 id="candidates" className="text-sm font-semibold">
            Is this the company?
          </h3>
          <p className="mt-1 text-xs text-ink-3">
            These entries from public datasets could not be matched by website. Nothing is used
            until you confirm.
          </p>
          <ul className="mt-2 flex flex-col gap-2">
            {data.candidates.map((c) => (
              <li
                key={c.company_enrichment_candidate_id}
                className="flex flex-wrap items-center justify-between gap-2"
              >
                <div>
                  <div className="font-medium">{c.label}</div>
                  <div className="text-xs text-ink-3">
                    {c.source_name} {c.external_id}
                    {c.description && ` · ${c.description}`}
                    {c.website && ` · ${c.website}`}
                  </div>
                  {candidateUrl(c.source_name, c.external_id) && (
                    <a
                      href={candidateUrl(c.source_name, c.external_id)!}
                      target="_blank"
                      rel="noopener noreferrer"
                      aria-label={`View on Wikidata: ${c.label}`}
                      className="text-xs underline"
                    >
                      View on Wikidata ↗
                    </a>
                  )}
                </div>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    disabled={decide.isPending}
                    onClick={() =>
                      decide.mutate({
                        candidateId: c.company_enrichment_candidate_id,
                        decision: 'confirm',
                      })
                    }
                  >
                    Yes, this is it
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={decide.isPending}
                    onClick={() =>
                      decide.mutate({
                        candidateId: c.company_enrichment_candidate_id,
                        decision: 'reject',
                      })
                    }
                  >
                    No
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section aria-labelledby="facts" className="rounded-lg border border-line bg-surface p-4">
        <h3 id="facts" className="mb-1 text-sm font-semibold">
          What is known
        </h3>
        {data.facts.filter((f) => !HIDDEN.has(f.fact_key)).length === 0 ? (
          <p className="text-sm text-ink-2">
            Nothing is known beyond the job board yet. Facts appear when a public dataset is
            matched.
          </p>
        ) : (
          <ul className="text-sm">
            {data.facts
              .filter((f) => !HIDDEN.has(f.fact_key))
              .map((f) => (
                <Fact key={f.fact_key} fact={f} />
              ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="hiring" className="rounded-lg border border-line bg-surface p-4">
        <h3 id="hiring" className="mb-2 text-sm font-semibold">
          Hiring activity
        </h3>
        <HiringChart weeks={data.hiring} />
      </section>

      <section aria-labelledby="offers" className="rounded-lg border border-line bg-surface p-4">
        <h3 id="offers" className="mb-1 text-sm font-semibold">
          Offers ({data.offers.length})
        </h3>
        {data.offers.length === 0 ? (
          <p className="text-sm text-ink-2">No offers collected yet.</p>
        ) : (
          <ul className="text-sm">
            {data.offers.map((o) => (
              <li
                key={o.job_opportunity_id}
                className="flex flex-wrap items-center justify-between gap-2 border-t border-line py-1.5 first:border-t-0"
              >
                <a
                  className="font-medium underline"
                  href={o.source_url}
                  target="_blank"
                  rel="noreferrer noopener"
                >
                  {o.title}
                </a>
                <span className="text-xs text-ink-3">
                  <span>{o.fit_score !== null ? `Fit ${o.fit_score}` : 'Not evaluated'}</span>
                  {' · '}
                  {formatAge(o.first_seen_at)} ago
                  {o.closed && <span className="ml-1 rounded bg-surface-2 px-1">Closed</span>}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {data.boards.length > 0 && (
        <p className="text-xs text-ink-3">
          Boards: {data.boards.map((b) => b.display_name).join(', ')}
        </p>
      )}
    </section>
  )
}
