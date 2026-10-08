import { useState } from 'react'
import { Link } from 'react-router'
import { Button } from '@/components/ui/button'
import { useAiSettings } from '@/features/ai/queries'
import type { ProfileRead } from '@/features/profile/queries'
import { useImportActions, type DocumentRead, type ProposalRead } from './queries'
import { ProposalReview } from './ProposalReview'

const kilobytes = (bytes: number) => `${Math.max(1, Math.round(bytes / 1024))} KB`

/**
 * Import a CV: upload (the original is not stored), generate proposals with the connection chosen
 * in AI & privacy (a remote provider needs confirmation for this CV), then review every proposed
 * fact. Applying the review creates the next profile revision.
 */
export function ImportCvPanel({ profile }: { profile: ProfileRead }) {
  const settings = useAiSettings()
  const actions = useImportActions(profile.career_profile_id)
  const [fileName, setFileName] = useState('')
  const [document, setDocument] = useState<DocumentRead | null>(null)
  const [proposal, setProposal] = useState<ProposalRead | null>(null)
  const [agreed, setAgreed] = useState(false)
  const [applied, setApplied] = useState<string | null>(null)

  const ai = settings.data
  const target = ai?.connections.find((c) => c.provider_connection_id === ai.import_connection_id)
  const remote = target?.processing_location === 'remote'
  const redact = ai?.privacy.redact_contact_details ?? true
  const error = [actions.upload, actions.propose, actions.review].find((m) => m.isError)?.error
  const revision = profile.current_revision?.revision_number ?? null

  function reset() {
    setDocument(null)
    setProposal(null)
    setAgreed(false)
    setApplied(null)
    actions.upload.reset()
    actions.propose.reset()
    actions.review.reset()
  }

  if (settings.isPending) return <p className="text-ink-3">Loading…</p>

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-2 text-xs">
        <span className="rounded bg-brand-soft px-2 py-0.5 text-brand-text">
          Original file is not stored
        </span>
        <span className="rounded bg-surface-2 px-2 py-0.5">
          Processing:{' '}
          {target
            ? remote
              ? `remote · ${target.display_name} · ${target.model_id}`
              : `this machine · ${target.model_id}`
            : 'none'}
        </span>
        {remote && redact && (
          <span className="rounded bg-surface-2 px-2 py-0.5">
            Contact details removed before sending
          </span>
        )}
      </div>

      {!target && (
        <p className="rounded-md border border-line bg-surface px-4 py-3 text-sm text-ink-2">
          Choose an AI connection for CV import in{' '}
          <Link className="underline" to="/settings">
            AI & privacy
          </Link>{' '}
          first. Without AI you can still fill in your profile by hand.
        </p>
      )}

      <div className="rounded-lg border border-dashed border-line-strong bg-surface px-4 py-5">
        <label className="flex flex-col gap-2 text-sm">
          <span className="font-semibold">Choose a CV file</span>
          <span className="text-ink-2">PDF (with text), DOCX, TXT or Markdown · up to 5 MB</span>
          <input
            type="file"
            aria-label="Choose a CV file"
            accept=".pdf,.docx,.txt,.md"
            disabled={!target || actions.upload.isPending}
            onChange={(event) => {
              const file = event.target.files?.[0]
              if (!file) return
              reset()
              setFileName(file.name)
              actions.upload.mutate(file, { onSuccess: setDocument })
            }}
          />
        </label>
      </div>

      {error && (
        <p role="alert" className="rounded-md bg-bad-bg px-3.5 py-2 text-sm text-bad">
          {error.message}
        </p>
      )}

      {document && document.extraction_status === 'needs_ocr' && (
        <p className="rounded-md bg-surface-2 px-3.5 py-2 text-sm">
          {fileName} has no text (it looks like a scan). OCR is not available; export the CV with
          text, or save it as a .txt file, and try again.
        </p>
      )}

      {document && document.extraction_status === 'extracted' && !proposal && (
        <section className="rounded-lg border border-line bg-surface p-4">
          <p className="text-sm">
            <strong>{fileName}</strong> · {kilobytes(document.byte_size)}
            {document.pages ? ` · ${document.pages} pages` : ''} · {document.characters} characters
            read
          </p>
          {remote && target && (
            <fieldset
              aria-label="Before this CV leaves your machine"
              className="mt-3 rounded-md border border-caution/50 bg-surface-2 p-3 text-sm"
              role="group"
            >
              <legend className="px-1 text-xs font-semibold text-ink-2">
                Before this CV leaves your machine
              </legend>
              <ul className="flex flex-col gap-0.5 text-ink-2">
                <li>Content: the text of this CV</li>
                <li>
                  Sent to: {target.display_name} · model {target.model_id} (remote)
                </li>
                <li>
                  {redact
                    ? 'Contact details are removed (e-mail, phone, links); your name and places stay.'
                    : 'Contact details are not removed (you turned redaction off).'}
                </li>
                <li>Why: to propose profile facts that you review before they count.</li>
              </ul>
              <label className="mt-2 flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={agreed}
                  onChange={(e) => setAgreed(e.target.checked)}
                />
                I agree to send this CV to {target.display_name}
              </label>
            </fieldset>
          )}
          <div className="mt-3">
            <Button
              disabled={(remote && !agreed) || actions.propose.isPending}
              onClick={() =>
                actions.propose.mutate(
                  {
                    documentId: document.document_id,
                    consent:
                      remote && target
                        ? {
                            provider_connection_id: target.provider_connection_id,
                            model_id: target.model_id ?? '',
                          }
                        : null,
                  },
                  { onSuccess: setProposal },
                )
              }
            >
              Generate proposals
            </Button>
            {actions.propose.isPending && (
              <span role="status" className="ml-3 text-sm text-ink-3">
                Reading your CV…
              </span>
            )}
          </div>
        </section>
      )}

      {proposal && !applied && (
        <ProposalReview
          items={proposal.items}
          applying={actions.review.isPending}
          revisionNumber={revision}
          onApply={(decisions) =>
            actions.review.mutate(
              { proposalId: proposal.profile_proposal_id, expectedRevision: revision, decisions },
              {
                onSuccess: (result) => {
                  const number = result.profile?.current_revision?.revision_number
                  setApplied(
                    result.created
                      ? `Revision ${number} was created from your review.`
                      : 'Your decisions were saved. Nothing changed in the profile.',
                  )
                  setProposal(result.proposal)
                },
              },
            )
          }
        />
      )}

      {applied && (
        <p role="status" className="rounded-md bg-good-bg px-3.5 py-2 text-sm text-good">
          {applied}{' '}
          <button type="button" className="underline" onClick={reset}>
            Import another CV
          </button>
        </p>
      )}
    </div>
  )
}
