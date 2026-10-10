import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'
import { unwrap } from '@/api/errors'
import { Button } from '@/components/ui/button'
import { useProfiles } from '@/features/profile/queries'
import type { InboxDetail } from './queries'

/** True when the score has no career-direction judgement for this job (it counts as not assessed). */
function notAssessed(dimensions: InboxDetail['dimensions']): boolean {
  const found = dimensions.find((d) => d.dimension_key === 'career_direction')
  const reason = found?.evidence.reason
  return Boolean(found?.excluded && typeof reason === 'string' && /not assessed/i.test(reason))
}

/**
 * Lets the owner assess one job against their career directions on demand (older jobs are never
 * judged in bulk, ADR-057). Shown only when a direction is enabled and the job has no judgement.
 */
export function AssessDirections({
  jobPostingId,
  dimensions,
}: {
  jobPostingId: number
  dimensions: InboxDetail['dimensions']
}) {
  const queryClient = useQueryClient()
  const { data: profiles } = useProfiles()
  const assess = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST('/api/v1/jobs/{job_posting_id}/assess-directions', {
          params: { path: { job_posting_id: jobPostingId } },
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['inbox'] }),
  })
  const hasEnabled = (profiles ?? []).some((profile) =>
    (profile.current_revision?.facts.directions ?? []).some((d) => d.enabled),
  )
  if (assess.data) {
    const { judged } = assess.data
    return (
      <p className="mt-2 text-xs text-ink-2" role="status">
        Assessed: {judged} {judged === 1 ? 'direction' : 'directions'} judged.
      </p>
    )
  }
  if (!hasEnabled || !notAssessed(dimensions)) return null
  return (
    <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-ink-2">
      <span>Career direction: not assessed.</span>
      <Button
        variant="outline"
        size="sm"
        disabled={assess.isPending}
        onClick={() => assess.mutate()}
      >
        {assess.isPending ? 'Assessing…' : 'Assess this job'}
      </Button>
      {assess.error && (
        <span role="alert" className="text-bad">
          The local model could not assess this job: {assess.error.message}
        </span>
      )}
    </div>
  )
}
