import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { formatAge, formatDateTime } from '@/lib/format'
import { AnalysisCard, WebsiteForm } from './CompanyAnalysis'
import { FollowStar } from './CompanyList'
import { HiringChart } from './HiringChart'
import { OfferList } from './OfferList'
import { useDossier, useDossierActions, useFollow, useIgnoreCompany, type Dossier } from './queries'

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
}
// The analysis and the summary have their own cards, so they are not repeated as plain facts.
const HIDDEN = new Set(['homepage', 'ai_dossier', 'ai_summary'])

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
    <li className="grid grid-cols-1 gap-1 sm:grid-cols-[130px_1fr] sm:gap-3 border-t border-line py-2 first:border-t-0">
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
export function DossierPanel({
  companyId,
  recencyDays = 30,
}: {
  companyId: number
  recencyDays?: number
}) {
  const [includeOlder, setIncludeOlder] = useState(false)
  const { data, isPending, isError } = useDossier(companyId, includeOlder)
  const follow = useFollow()
  const ignore = useIgnoreCompany()
  const { enrich, summarise, analyse, setWebsite, decide } = useDossierActions(companyId)
  const [step, setStep] = useState<string | null>(null)
  const [stepErrors, setStepErrors] = useState<string[]>([])
  const [editingWebsite, setEditingWebsite] = useState(false)
  const attempted = useRef(new Set<number>())

  useEffect(() => {
    if (data?.stale && !attempted.current.has(companyId)) {
      attempted.current.add(companyId)
      enrich.mutate()
    }
  }, [data?.stale, companyId, enrich])

  /**
   * "Update info": public sources, then the website analysis, then the summary, one after the
   * other (the summary reads what the first two found). A step that fails is reported and does not
   * stop the next one.
   */
  async function updateInfo() {
    const steps: [string, () => Promise<unknown>, boolean][] = [
      ['Looking up public sources…', () => enrich.mutateAsync(), true],
      [
        'Reading the company website with the local model. This can take a few minutes…',
        () => analyse.mutateAsync(),
        !!data?.homepage_url,
      ],
      ['Writing the summary…', () => summarise.mutateAsync(), true],
    ]
    const errors: string[] = []
    for (const [label, run, enabled] of steps) {
      if (!enabled) continue
      setStep(label)
      try {
        await run()
      } catch (error) {
        errors.push(error instanceof Error ? error.message : 'A step failed.')
      }
    }
    setStep(null)
    // The same cause (for example no local model) often fails several steps: say it once.
    setStepErrors([...new Set(errors)])
  }

  if (isPending) return <p className="p-6 text-ink-3">Loading…</p>
  if (isError)
    return (
      <p role="alert" className="p-6 text-bad">
        Could not load this company.
      </p>
    )
  const failure = [setWebsite, decide, ignore].find((m) => m.isError)?.error
  const summary = data.facts.find((f) => f.fact_key === 'ai_summary')
  const dossier = data.facts.find((f) => f.fact_key === 'ai_dossier')
  const host = data.homepage_url ? new URL(data.homepage_url).hostname.replace(/^www\./, '') : null

  return (
    <section aria-label={data.name} className="flex flex-col gap-4 p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-2">
          <FollowStar
            size="lg"
            name={data.name}
            followed={data.is_followed}
            disabled={follow.isPending}
            onToggle={() => follow.mutate({ companyId, follow: !data.is_followed })}
          />
          <div>
            <h2 className="text-lg font-semibold">
              {data.name}
              {data.is_ignored && (
                <span className="ml-2 rounded-full bg-bad-bg px-2 text-xs font-medium text-bad">
                  Ignored
                </span>
              )}
            </h2>
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
              <button
                type="button"
                className="ml-2 text-xs underline"
                onClick={() => setEditingWebsite((v) => !v)}
              >
                {data.homepage_url ? 'Change' : 'Add website'}
              </button>
              {data.enriched_at && (
                <span className="ml-2 text-ink-3">checked {formatAge(data.enriched_at)} ago</span>
              )}
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button
            size="sm"
            variant="outline"
            disabled={ignore.isPending}
            title={
              data.is_ignored
                ? 'Restore the offers that ignoring this company moved'
                : 'Move all its offers to Ignored, now and when they appear'
            }
            onClick={() => ignore.mutate({ companyId, ignore: !data.is_ignored })}
          >
            {data.is_ignored ? 'Stop ignoring company' : 'Ignore company'}
          </Button>
          <Button
            size="sm"
            disabled={step !== null}
            title="Looks up public sources, reads the company website and writes a summary"
            onClick={() => void updateInfo()}
          >
            Update info
          </Button>
        </div>
      </div>
      {(editingWebsite || !data.homepage_url) && (
        <WebsiteForm
          pending={setWebsite.isPending}
          onSubmit={(url) => setWebsite.mutate(url, { onSuccess: () => setEditingWebsite(false) })}
        />
      )}
      {step && (
        <p role="status" className="text-sm text-ink-3">
          {step}
        </p>
      )}
      {stepErrors.map((message) => (
        <p key={message} role="alert" className="rounded-md bg-bad-bg px-3 py-2 text-sm text-bad">
          {message}
        </p>
      ))}
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
            This lists facts from public datasets (Wikidata, Wikipedia, GLEIF, GitHub), and only
            once the company is identified there. None has been found yet: add the company website
            and press “Update info”, or confirm one of the candidates above. The website analysis
            has its own card below.
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

      {summary && (
        <section aria-labelledby="about" className="rounded-lg border border-line bg-surface p-4">
          <h3 id="about" className="mb-1 text-sm font-semibold">
            About
          </h3>
          <p className="text-sm">{factText(summary.value)}</p>
          <p className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-ink-3">
            <span className="rounded bg-caution/20 px-1.5 py-px font-medium text-ink">
              AI inference
            </span>
            <span>{summary.source_name}</span>
            <span>{formatDateTime(summary.retrieved_at)}</span>
          </p>
        </section>
      )}

      <section aria-labelledby="analysis" className="rounded-lg border border-line bg-surface p-4">
        <h3 id="analysis" className="mb-2 text-sm font-semibold">
          Company analysis
        </h3>
        {dossier ? (
          <AnalysisCard
            value={dossier.value}
            model={dossier.source_name}
            retrievedAt={dossier.retrieved_at}
          />
        ) : (
          <p className="text-sm text-ink-2">
            Not analysed yet. “Update info” reads a few public pages of the company site and writes
            a cited profile with the local model.
          </p>
        )}
      </section>

      <section aria-labelledby="hiring" className="rounded-lg border border-line bg-surface p-4">
        <h3 id="hiring" className="mb-2 text-sm font-semibold">
          Hiring activity
        </h3>
        <HiringChart weeks={data.hiring} />
      </section>

      <OfferList
        offers={data.offers}
        recencyDays={recencyDays}
        includeOlder={includeOlder}
        truncated={data.offers_truncated}
        onOlderChange={setIncludeOlder}
      />

      {data.boards.length > 0 && (
        <p className="text-xs text-ink-3">
          Boards: {data.boards.map((b) => b.display_name).join(', ')}
        </p>
      )}
    </section>
  )
}
