import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'
import { unwrap } from '@/api/errors'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { InboxDetail } from './queries'

/** How many technologies show before the "+N more" button (the stack is read at a glance). */
const VISIBLE_TECHNOLOGIES = 8

type Brief = InboxDetail['brief']

function Technologies({ technologies }: { technologies: Brief['technologies'] }) {
  const [all, setAll] = useState(false)
  if (technologies.length === 0) return null
  const shown = all ? technologies : technologies.slice(0, VISIBLE_TECHNOLOGIES)
  const hidden = technologies.length - shown.length
  return (
    <div className="mt-3">
      <h4 className="mb-1.5 text-sm font-semibold tracking-wider text-ink-3 uppercase">
        Technologies{' '}
        <span className="font-normal tracking-normal normal-case">
          · solid = required, dashed = preferred
        </span>
      </h4>
      <ul aria-label="Technologies" className="flex flex-wrap gap-1.5">
        {shown.map((tech) => (
          <li
            key={tech.name}
            className={cn(
              'rounded-md border px-2 py-px text-sm',
              tech.importance === 'must'
                ? 'border-line-strong bg-surface-2 font-semibold'
                : 'border-dashed border-line-strong text-ink-2',
            )}
          >
            {tech.name}
            {/* Text as well as style, so the difference never depends on how a border looks. */}
            <span className="sr-only">
              {tech.importance === 'must' ? ' (required)' : ' (preferred)'}
            </span>
          </li>
        ))}
        {hidden > 0 && (
          <li>
            <Button variant="ghost" size="sm" onClick={() => setAll(true)}>
              +{hidden} more
            </Button>
          </li>
        )}
      </ul>
    </div>
  )
}

/**
 * The briefing above the full description (ADR-059): the key facts on one line, the AI summary in
 * one or two paragraphs (or a note and a button when it has not been written yet) and the main
 * technologies. Everything comes from stored rows; only the button calls the local model.
 */
export function JobBrief({ brief, jobPostingId }: { brief: Brief; jobPostingId: number }) {
  const queryClient = useQueryClient()
  const write = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST('/api/v1/jobs/{job_posting_id}/summary', {
          params: { path: { job_posting_id: jobPostingId } },
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['inbox'] }),
  })
  // A summary just written shows at once; the refetch then brings the stored one with its model.
  const summary = brief.summary ?? write.data?.summary ?? null
  return (
    <section className="border-b border-line px-5 py-4" aria-label="Job briefing">
      {brief.facts.length > 0 && (
        <p aria-label="Key facts" className="mb-2 text-base font-medium">
          {brief.facts.join(' · ')}
        </p>
      )}
      {summary ? (
        <div className="flex flex-col gap-2 text-base leading-relaxed">
          {summary.split(/\n\n+/).map((paragraph) => (
            <p key={paragraph}>{paragraph}</p>
          ))}
          <span
            className="self-start rounded-full border border-line-strong px-2 py-px text-sm text-ink-3"
            title={
              brief.summary_model
                ? `Written by ${brief.summary_model}; check the full description`
                : 'Written by the local model; check the full description'
            }
          >
            AI summary
          </span>
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-2 text-base text-ink-2">
          <span>The summary has not been generated yet.</span>
          <Button
            variant="outline"
            size="sm"
            disabled={write.isPending}
            onClick={() => write.mutate()}
          >
            {write.isPending ? 'Writing…' : 'Generate summary'}
          </Button>
          {write.error && (
            <span role="alert" className="text-bad">
              The local model could not write the summary: {write.error.message}
            </span>
          )}
        </div>
      )}
      <Technologies technologies={brief.technologies} />
    </section>
  )
}
