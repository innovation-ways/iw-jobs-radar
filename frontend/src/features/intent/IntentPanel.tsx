import { useEffect } from 'react'
import { DirtyBar } from '@/components/DirtyBar'
import { Button } from '@/components/ui/button'
import { useDraft } from '@/lib/useDraft'
import { useProfileActions, type IntentRead, type TaxonomyRead } from '@/features/profile/queries'
import { IntentForm } from './IntentForm'
import { intentProblem } from './validate'
import { WeightsPanel } from './WeightsPanel'

interface Props {
  intent: IntentRead
  taxonomy: TaxonomyRead
  section: 'intent' | 'weights'
  /** Reports whether the draft has unsaved changes, so the page can warn before switching. */
  onDirtyChange?: (dirty: boolean) => void
}

/**
 * Edits one intent as a draft shared by the Search intent and Scoring weights sections (weights
 * are part of the intent). Saving creates the next immutable revision.
 */
export function IntentPanel({ intent, taxonomy, section, onDirtyChange }: Props) {
  const revision = intent.current_revision
  const { saveIntent, setIntentEnabled } = useProfileActions()
  const { draft, setDraft, dirty, discard } = useDraft(
    revision!.definition,
    revision!.intent_revision_id,
  )
  useEffect(() => onDirtyChange?.(dirty), [dirty, onDirtyChange])

  const problem = intentProblem(draft)
  const error = saveIntent.error?.message ?? setIntentEnabled.error?.message ?? null

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-line bg-surface px-4 py-3">
        <p className="text-sm">
          <strong>{intent.title}</strong>
          <span className="ml-2 text-ink-3">revision {revision!.revision_number}</span>
          <span className="ml-3">
            {intent.enabled
              ? 'Enabled: included in the daily collection and digest.'
              : 'Disabled: not included in collection or digest.'}
          </span>
        </p>
        <Button
          variant="outline"
          size="sm"
          disabled={setIntentEnabled.isPending}
          onClick={() =>
            setIntentEnabled.mutate({
              profileId: intent.career_profile_id,
              intentId: intent.search_intent_id,
              version: intent.version,
              enabled: !intent.enabled,
            })
          }
        >
          {intent.enabled ? 'Disable' : 'Enable'}
        </Button>
      </div>
      {section === 'intent' ? (
        <IntentForm value={draft} onChange={setDraft} taxonomy={taxonomy} />
      ) : (
        <WeightsPanel
          value={draft.weights}
          onChange={(weights) => setDraft({ ...draft, weights })}
        />
      )}
      <DirtyBar
        dirty={dirty}
        saving={saveIntent.isPending}
        problem={problem}
        error={error}
        onDiscard={() => {
          saveIntent.reset()
          discard()
        }}
        onSave={(summary) =>
          saveIntent.mutate({
            profileId: intent.career_profile_id,
            intentId: intent.search_intent_id,
            definition: draft,
            expected: revision!.revision_number,
            summary: summary || undefined,
          })
        }
      />
    </>
  )
}
