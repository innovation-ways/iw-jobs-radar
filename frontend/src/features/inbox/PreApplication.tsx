import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'
import { unwrap } from '@/api/errors'
import type { components } from '@/api/schema'
import { Button } from '@/components/ui/button'
import { formatDateTime } from '@/lib/format'

type Draft = components['schemas']['ApplicationDraftRead']

function DraftView({ draft }: { draft: Draft }) {
  const [copied, setCopied] = useState(false)
  const { strengths, positioning, cover_letter, letter_language } = draft.draft
  // The API schema marks a defaulted list as optional; a draft without gaps simply has none.
  const gaps = draft.draft.gaps ?? []
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(cover_letter)
      setCopied(true)
    } catch {
      // A browser that refuses the clipboard leaves the text selectable on the screen.
      setCopied(false)
    }
  }
  return (
    <div className="mt-3 flex flex-col gap-4 text-base">
      <div>
        <h4 className="mb-1.5 text-sm font-semibold tracking-wider text-ink-3 uppercase">
          Strengths to stress
        </h4>
        <ul className="flex flex-col gap-1.5">
          {strengths.map((s) => (
            <li key={s.point}>
              <span className="font-medium">{s.point}</span>
              <span className="block text-sm text-ink-3">Based on: {s.evidence}</span>
            </li>
          ))}
        </ul>
      </div>
      <div>
        <h4 className="mb-1.5 text-sm font-semibold tracking-wider text-ink-3 uppercase">
          How to present yourself
        </h4>
        <p className="leading-relaxed">{positioning}</p>
      </div>
      {gaps.length > 0 && (
        <div>
          <h4 className="mb-1.5 text-sm font-semibold tracking-wider text-ink-3 uppercase">
            Gaps to address
          </h4>
          <ul className="list-disc pl-5">
            {gaps.map((g) => (
              <li key={g}>{g}</li>
            ))}
          </ul>
        </div>
      )}
      <div>
        <div className="mb-1.5 flex flex-wrap items-center gap-2">
          <h4 className="text-sm font-semibold tracking-wider text-ink-3 uppercase">
            Cover letter base · {letter_language === 'pt' ? 'Portuguese' : 'English'}
          </h4>
          <Button variant="outline" size="sm" onClick={copy}>
            Copy letter
          </Button>
          {copied && <span className="text-sm text-ink-3">Copied</span>}
        </div>
        <div
          aria-label="Cover letter"
          className="rounded-md border border-line bg-surface-2 px-3 py-2 leading-relaxed whitespace-pre-wrap"
        >
          {cover_letter}
        </div>
      </div>
    </div>
  )
}

/**
 * The pre-application section of the detail (ADR-064): a button that asks the local model, on
 * request only, for the strengths to stress, how to present oneself, the gaps and a cover-letter
 * base. The newest stored draft shows at once; another can be written without losing the first.
 * The text is an AI draft written from the profile facts and the posting, labelled as such.
 *
 * @param jobPostingId - the job the draft is for
 */
export function PreApplication({ jobPostingId }: { jobPostingId: number }) {
  const queryClient = useQueryClient()
  const key = ['application-drafts', jobPostingId]
  const drafts = useQuery({
    queryKey: key,
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/jobs/{job_posting_id}/application-drafts', {
          params: { path: { job_posting_id: jobPostingId } },
        }),
      ),
  })
  const write = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST('/api/v1/jobs/{job_posting_id}/application-draft', {
          params: { path: { job_posting_id: jobPostingId } },
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: key }),
  })
  // A draft just written shows at once; the refetch then brings the stored list.
  const newest = write.data ?? drafts.data?.items[0] ?? null
  return (
    <section className="border-b border-line px-5 py-4" aria-label="Pre-application">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold tracking-wider text-ink-3 uppercase">
          Pre-application
        </h3>
        <Button
          variant="outline"
          size="sm"
          disabled={write.isPending}
          onClick={() => write.mutate()}
        >
          {write.isPending ? 'Writing…' : newest ? 'Write another' : 'Pre-application'}
        </Button>
        {newest && (
          <span
            className="rounded-full border border-line-strong px-2 py-px text-sm text-ink-3"
            title={`Written by ${newest.model} on ${formatDateTime(newest.created_at)}`}
          >
            AI draft: check every claim before sending
          </span>
        )}
      </div>
      {write.error && (
        <p role="alert" className="mt-2 text-base text-bad">
          The local model could not write the draft: {write.error.message}
        </p>
      )}
      {newest && <DraftView draft={newest} />}
    </section>
  )
}
