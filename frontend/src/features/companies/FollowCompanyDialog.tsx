import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import {
  useDetectCompany,
  useFollowCompany,
  sourceLabel,
  useProposeReader,
  type DetectedBoard,
  type Detection,
  type FollowForm,
  type ReaderProposal,
} from './onboarding'

const NO_COLLECTION: Record<string, { title: string; note: string }> = {
  unsupported: {
    title: 'No supported system found',
    note: 'The careers page uses a system that is not supported yet (for example Workday or Teamtailor).',
  },
  script_only: {
    title: 'The postings are loaded by JavaScript',
    note: 'The page has no postings in its HTML and no structured data; they are searched in the browser.',
  },
  blocked: {
    title: 'The careers page cannot be read',
    note: 'Jobs Radar respects the site’s rules and does not work around a refusal.',
  },
  unreachable: {
    title: 'The careers page did not answer',
    note: 'Try again later; you can still follow the company without collection.',
  },
}

function Field({
  id,
  label,
  hint,
  value,
  error,
  placeholder,
  onChange,
}: {
  id: string
  label: string
  hint: string
  value: string
  error?: string
  placeholder?: string
  onChange: (value: string) => void
}) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-[13px] font-semibold">
        {label}{' '}
        <span aria-hidden="true" className="text-bad">
          *
        </span>
      </label>
      <input
        id={id}
        value={value}
        placeholder={placeholder}
        autoComplete="off"
        spellCheck={false}
        aria-invalid={error ? true : undefined}
        aria-describedby={`${id}-hint`}
        onChange={(event) => onChange(event.target.value)}
        className={cn(
          'rounded-md border bg-surface px-2.5 py-1.5 text-sm',
          error ? 'border-bad' : 'border-line-strong',
        )}
      />
      <span id={`${id}-hint`} className="text-xs text-ink-3">
        {hint}
      </span>
      {error && (
        <span role="alert" className="text-xs text-bad">
          {error}
        </span>
      )}
    </div>
  )
}

/**
 * "Follow a company" (ADR-070): the owner gives the company's name, website and careers page, the
 * app checks what the careers page can be collected from, and nothing is saved until the owner
 * confirms. A page with no known board can get a reader proposed by the local model, which the
 * owner reviews before approving. `initial` prefills the form for "Detect again".
 */
export function FollowCompanyDialog({
  initial,
  onClose,
  onDone,
}: {
  initial?: FollowForm
  onClose: () => void
  onDone: (companyId: number) => void
}) {
  const [form, setForm] = useState<FollowForm>(
    initial ?? { name: '', websiteUrl: '', careersUrl: '' },
  )
  const [errors, setErrors] = useState<Partial<Record<keyof FollowForm, string>>>({})
  const [filtersEnabled, setFiltersEnabled] = useState(true)
  const [detection, setDetection] = useState<Detection | null>(null)
  const [chosen, setChosen] = useState(0)
  const [proposal, setProposal] = useState<ReaderProposal | null>(null)
  const detect = useDetectCompany()
  const propose = useProposeReader()
  const follow = useFollowCompany()
  const dialog = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    dialog.current?.querySelector('input')?.focus()
    const close = (event: KeyboardEvent) => event.key === 'Escape' && onClose()
    window.addEventListener('keydown', close)
    return () => window.removeEventListener('keydown', close)
  }, [onClose])

  function reset() {
    setDetection(null)
    setProposal(null)
    setChosen(0)
    detect.reset()
    propose.reset()
    follow.reset()
  }

  function check(event: FormEvent) {
    event.preventDefault()
    const next: Partial<Record<keyof FollowForm, string>> = {}
    if (!form.name.trim()) next.name = 'Enter the company name.'
    if (!form.websiteUrl.trim()) next.websiteUrl = 'Enter the company website.'
    if (!form.careersUrl.trim()) next.careersUrl = 'Enter the careers page address.'
    setErrors(next)
    if (Object.keys(next).length > 0) return
    reset()
    detect.mutate(form, { onSuccess: (result) => setDetection(result) })
  }

  const boards: DetectedBoard[] = detection?.candidates ?? []
  const board = boards[chosen]
  const collectable = detection?.outcome === 'detected' || detection?.outcome === 'ambiguous'
  const canPropose = detection?.outcome === 'unsupported'
  const busy = detect.isPending || propose.isPending || follow.isPending

  function confirm() {
    follow.mutate(
      {
        form,
        filtersEnabled,
        ...(proposal ? { reader: proposal } : collectable && board ? { board } : {}),
      },
      { onSuccess: (result) => onDone(result.company_id) },
    )
  }

  const confirmLabel = proposal
    ? 'Approve reader and follow'
    : collectable
      ? 'Follow and collect now'
      : 'Follow without collection'
  const canConfirm = detection !== null && detection.outcome !== 'already_followed' && !busy
  const problem = detect.error?.message ?? propose.error?.message ?? follow.error?.message

  return (
    <div
      className="fixed inset-0 z-30 flex items-start justify-center overflow-y-auto bg-black/40 p-4 pt-10"
      onClick={(event) => event.target === event.currentTarget && onClose()}
    >
      <div
        ref={dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="follow-title"
        className="w-[620px] max-w-full rounded-xl border border-line bg-surface shadow-lg"
      >
        <header className="flex items-center gap-2 border-b border-line px-4 py-3">
          <h2 id="follow-title" className="flex-1 text-base font-semibold">
            Follow a company
          </h2>
          <Button variant="outline" size="sm" onClick={onClose}>
            Close
          </Button>
        </header>

        <form onSubmit={check} noValidate className="flex flex-col gap-3.5 p-4">
          <Field
            id="follow-name"
            label="Company name"
            hint="How it is listed in Jobs Radar. If a company with this name already exists, the new source is attached to it."
            value={form.name}
            error={errors.name}
            onChange={(name) => setForm({ ...form, name })}
          />
          <Field
            id="follow-site"
            label="Company website"
            hint="The company’s own site. It is used to analyse the company (dossier) and to identify it in open data."
            placeholder="https://example.com"
            value={form.websiteUrl}
            error={errors.websiteUrl}
            onChange={(websiteUrl) => setForm({ ...form, websiteUrl })}
          />
          <Field
            id="follow-careers"
            label="Careers page"
            hint="Where the company publishes its offers. A board address such as jobs.lever.co/acme works too."
            placeholder="https://example.com/careers"
            value={form.careersUrl}
            error={errors.careersUrl}
            onChange={(careersUrl) => setForm({ ...form, careersUrl })}
          />
          <label className="flex items-start gap-2.5 rounded-lg border border-line bg-surface-2 p-2.5 text-sm">
            <input
              type="checkbox"
              checked={filtersEnabled}
              onChange={(event) => setFiltersEnabled(event.target.checked)}
              className="mt-1"
            />
            <span>
              <b className="font-semibold">Keep only postings that match my areas and location</b>
              <br />
              <span className="text-xs text-ink-3">
                Recommended for large employers (hundreds of postings). Uses your profile and Search
                Intent; you can change it later in Sources.
              </span>
            </span>
          </label>
          <div className="flex items-center gap-3">
            <Button type="submit" variant="outline" disabled={busy}>
              {detect.isPending ? 'Checking…' : 'Check addresses'}
            </Button>
            <span className="text-xs text-ink-3">Nothing is saved until you confirm.</span>
          </div>
        </form>

        <div aria-live="polite" className="flex flex-col gap-3 px-4 pb-4">
          {problem && (
            <p role="alert" className="rounded-md bg-bad-bg px-3 py-2 text-sm text-bad">
              {problem}
            </p>
          )}

          {detection && collectable && !proposal && (
            <div className="rounded-lg border border-line">
              <p className="rounded-t-lg bg-good-bg px-3 py-2 text-sm font-semibold text-good">
                {boards.length === 1
                  ? 'Found a source to collect from'
                  : 'More than one board was found'}
              </p>
              <div className="flex flex-col gap-2 p-3">
                {boards.map((candidate, index) => (
                  <label
                    key={`${candidate.source_type}:${candidate.identifier}`}
                    className={cn(
                      'flex items-start gap-2.5 rounded-md border p-2 text-sm',
                      index === chosen ? 'border-brand bg-brand-soft' : 'border-line',
                    )}
                  >
                    <input
                      type="radio"
                      name="board"
                      checked={index === chosen}
                      onChange={() => setChosen(index)}
                      className="mt-1"
                    />
                    <span>
                      {sourceLabel(candidate.source_type)} <code>{candidate.identifier}</code>
                      <br />
                      <span className="text-xs text-ink-3 tabular-nums">
                        {candidate.postings_count} open postings
                        {candidate.layer === 'structured_page' && ' (pages found in the sitemap)'}
                      </span>
                    </span>
                  </label>
                ))}
              </div>
            </div>
          )}

          {detection && !collectable && detection.outcome !== 'already_followed' && !proposal && (
            <div className="rounded-lg border border-line">
              <p className="rounded-t-lg bg-caution-bg px-3 py-2 text-sm font-semibold text-caution">
                {NO_COLLECTION[detection.outcome]?.title ?? 'Nothing to collect from'}
              </p>
              <div className="flex flex-col gap-2 p-3 text-sm">
                <p>Collected automatically: no.</p>
                <p className="text-ink-2">
                  {detection.reason ?? NO_COLLECTION[detection.outcome]?.note}
                </p>
                <p className="rounded-md bg-surface-2 px-2.5 py-2 text-xs text-ink-2">
                  You can still follow the company: its website is analysed and its careers page is
                  linked. “Detect again” in the company repeats this check later.
                </p>
                {canPropose && (
                  <div>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={busy}
                      onClick={() =>
                        propose.mutate(form, { onSuccess: (result) => setProposal(result) })
                      }
                    >
                      {propose.isPending ? 'Asking the local model…' : 'Propose a reader'}
                    </Button>
                    <span className="ml-2 text-xs text-ink-3">
                      The local model suggests how to read this page; you review it first.
                    </span>
                  </div>
                )}
              </div>
            </div>
          )}

          {detection?.outcome === 'already_followed' && (
            <div className="rounded-lg border border-line">
              <p className="rounded-t-lg bg-caution-bg px-3 py-2 text-sm font-semibold text-caution">
                This company is already followed
              </p>
              <p className="p-3 text-sm text-ink-2">
                Nothing would change. Open the company to see its collection state or detect again.
              </p>
            </div>
          )}

          {proposal && (
            <div className="rounded-lg border border-line">
              <p className="rounded-t-lg bg-good-bg px-3 py-2 text-sm font-semibold text-good">
                A reader was proposed and finds {proposal.preview.length} postings on the page
              </p>
              <ul className="flex flex-col gap-1 p-3 text-sm">
                {proposal.preview.map((posting) => (
                  <li key={posting.url} className="flex flex-wrap gap-x-2">
                    <span className="font-medium">{posting.title}</span>
                    {posting.location && <span className="text-ink-3">{posting.location}</span>}
                  </li>
                ))}
              </ul>
              <p className="border-t border-line px-3 py-2 text-xs text-ink-3">
                Written by {proposal.proposed_by.split(':').slice(1, 3).join(' ')}. Later runs use
                these selectors with no AI; if the page changes you will be asked for a new one.
              </p>
            </div>
          )}
        </div>

        <footer className="flex items-center justify-end gap-2 rounded-b-xl border-t border-line bg-surface-2 px-4 py-3">
          {proposal && (
            <Button variant="ghost" size="sm" onClick={() => setProposal(null)}>
              Discard the reader
            </Button>
          )}
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!canConfirm} onClick={confirm}>
            {follow.isPending ? 'Saving…' : confirmLabel}
          </Button>
        </footer>
      </div>
    </div>
  )
}
