import { useQuery } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { Card } from '@/components/Card'
import { Button } from '@/components/ui/button'
import { formatDateTime } from '@/lib/format'
import {
  fetchProfileRevision,
  useIntentRevisions,
  useProfileActions,
  useProfileRevisions,
  type IntentRead,
  type ProfileRead,
} from '@/features/profile/queries'
import { diffRevisions } from './diff'

interface Row {
  id: number
  number: number
  createdAt: string
  summary: string | null
}

type Selection = { scope: 'profile' | 'intent'; id: number; mode: 'view' | 'compare' } | null

function Differences({ before, after }: { before: unknown; after: unknown }) {
  const differences = diffRevisions(before, after)
  if (differences.length === 0) {
    return <p className="text-sm text-ink-3">No differences: the content is identical.</p>
  }
  return (
    <ul aria-label="Differences" className="flex flex-col gap-1 text-sm">
      {differences.map((difference, index) => (
        <li key={index}>
          <span className="font-medium">{difference.path}</span>{' '}
          {difference.kind === 'changed' && (
            <>
              <span className="text-ink-3">{difference.before}</span> →{' '}
              <span>{difference.after}</span>
            </>
          )}
          {difference.kind === 'added' && (
            <span className="text-good">added: {difference.after}</span>
          )}
          {difference.kind === 'removed' && (
            <span className="text-bad">removed: {difference.before}</span>
          )}
        </li>
      ))}
    </ul>
  )
}

function Detail({ children, onClose }: { children: ReactNode; onClose: () => void }) {
  return (
    <div className="mt-3 rounded-md border border-line bg-surface-2 p-3">
      {children}
      <div className="mt-2 text-right">
        <Button variant="ghost" size="sm" onClick={onClose}>
          Close
        </Button>
      </div>
    </div>
  )
}

function RevisionTable({
  caption,
  rows,
  currentNumber,
  selection,
  scope,
  onSelect,
  onRestore,
  busy,
}: {
  caption: string
  rows: Row[]
  currentNumber: number | undefined
  selection: Selection
  scope: 'profile' | 'intent'
  onSelect: (selection: Selection) => void
  onRestore: (row: Row) => void
  busy: boolean
}) {
  return (
    <table className="w-full text-sm" aria-label={caption}>
      <thead>
        <tr className="text-left text-[11px] tracking-wider text-ink-3 uppercase">
          <th scope="col" className="py-1 font-semibold">
            Rev
          </th>
          <th scope="col" className="py-1 font-semibold">
            Date
          </th>
          <th scope="col" className="py-1 font-semibold">
            Change
          </th>
          <th scope="col" className="py-1">
            <span className="sr-only">Actions</span>
          </th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => {
          const current = row.number === currentNumber
          const active = selection?.scope === scope && selection.id === row.id
          return (
            <tr key={row.id} className={`border-t border-line ${active ? 'bg-surface-2' : ''}`}>
              <td className="py-2 pr-3 tabular-nums">
                <strong>{row.number}</strong>
                {current && (
                  <span className="ml-2 rounded-full bg-brand-soft px-2 py-0.5 text-xs text-brand-text">
                    current
                  </span>
                )}
              </td>
              <td className="py-2 pr-3 text-ink-2">{formatDateTime(row.createdAt)}</td>
              <td className="py-2 pr-3">{row.summary ?? <span className="text-ink-3">—</span>}</td>
              <td className="py-2 text-right whitespace-nowrap">
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={`View revision ${row.number}`}
                  onClick={() => onSelect({ scope, id: row.id, mode: 'view' })}
                >
                  View
                </Button>
                {!current && (
                  <>
                    <Button
                      variant="ghost"
                      size="sm"
                      aria-label={`Compare revision ${row.number} with the current one`}
                      onClick={() => onSelect({ scope, id: row.id, mode: 'compare' })}
                    >
                      Compare
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={busy}
                      aria-label={`Restore revision ${row.number}`}
                      onClick={() => onRestore(row)}
                    >
                      Restore
                    </Button>
                  </>
                )}
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

/**
 * Revision history of the profile and the intent. Revisions are append-only: Restore creates a
 * new revision with the old content, and Compare lists what differs from the current revision.
 */
export function HistoryPanel({
  profile,
  intent,
}: {
  profile: ProfileRead
  intent: IntentRead | null
}) {
  const profileRevisions = useProfileRevisions(profile.career_profile_id)
  const intentRevisions = useIntentRevisions(intent?.search_intent_id)
  const { restoreProfile, restoreIntent } = useProfileActions()
  const [selection, setSelection] = useState<Selection>(null)
  const [message, setMessage] = useState<string | null>(null)

  const currentProfile = profile.current_revision
  const profileDetail = useQuery({
    queryKey: [
      'profile-revision-detail',
      profile.career_profile_id,
      selection?.id,
      currentProfile?.profile_revision_id,
    ],
    enabled: selection?.scope === 'profile',
    queryFn: async () => ({
      selected: await fetchProfileRevision(profile.career_profile_id, selection!.id),
      current: currentProfile
        ? await fetchProfileRevision(profile.career_profile_id, currentProfile.profile_revision_id)
        : null,
    }),
  })

  const intentList = intentRevisions.data ?? []
  const selectedIntent =
    selection?.scope === 'intent'
      ? intentList.find((r) => r.intent_revision_id === selection.id)
      : undefined
  const currentIntent = intent?.current_revision

  const profileRows: Row[] = (profileRevisions.data ?? []).map((r) => ({
    id: r.profile_revision_id,
    number: r.revision_number,
    createdAt: r.created_at,
    summary: r.change_summary,
  }))
  const intentRows: Row[] = intentList.map((r) => ({
    id: r.intent_revision_id,
    number: r.revision_number,
    createdAt: r.created_at,
    summary: r.change_summary,
  }))

  const failure = restoreProfile.error?.message ?? restoreIntent.error?.message ?? null

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-ink-2">
        Revisions are append-only. “Restore” creates a new revision with the old content; nothing is
        overwritten.
      </p>
      {message && (
        <p role="status" className="rounded-md bg-brand-soft px-3.5 py-2 text-sm text-brand-text">
          {message}
        </p>
      )}
      {failure && (
        <p role="alert" className="rounded-md bg-bad-bg px-3.5 py-2 text-sm text-bad">
          {failure}
        </p>
      )}

      <Card title={`Profile revisions · ${profile.title}`}>
        {profileRevisions.isPending && <p className="text-sm text-ink-3">Loading…</p>}
        {profileRevisions.isError && (
          <p role="alert" className="text-sm text-bad">
            Could not load the revisions.
          </p>
        )}
        {profileRevisions.data && (
          <RevisionTable
            caption="Profile revisions"
            rows={profileRows}
            currentNumber={currentProfile?.revision_number}
            selection={selection}
            scope="profile"
            busy={restoreProfile.isPending}
            onSelect={(next) => {
              setMessage(null)
              setSelection(next)
            }}
            onRestore={(row) => {
              if (!currentProfile) return
              setMessage(null)
              restoreProfile.mutate(
                {
                  profileId: profile.career_profile_id,
                  revisionId: row.id,
                  expected: currentProfile.revision_number,
                },
                {
                  onSuccess: (result) =>
                    setMessage(
                      result.created
                        ? `Restored revision ${row.number} as revision ${result.profile.current_revision?.revision_number}.`
                        : 'That revision is identical to the current one; nothing was created.',
                    ),
                },
              )
            }}
          />
        )}
        {selection?.scope === 'profile' && (
          <Detail onClose={() => setSelection(null)}>
            {profileDetail.isPending && <p className="text-sm text-ink-3">Loading…</p>}
            {profileDetail.data &&
              (selection.mode === 'view' ? (
                <pre className="max-h-80 overflow-auto text-xs whitespace-pre-wrap">
                  {JSON.stringify(profileDetail.data.selected.facts, null, 2)}
                </pre>
              ) : (
                <Differences
                  before={profileDetail.data.selected.facts}
                  after={profileDetail.data.current?.facts}
                />
              ))}
          </Detail>
        )}
      </Card>

      {intent && (
        <Card title={`Intent revisions · ${intent.title}`}>
          {intentRevisions.isPending && <p className="text-sm text-ink-3">Loading…</p>}
          {intentRevisions.data && (
            <RevisionTable
              caption="Intent revisions"
              rows={intentRows}
              currentNumber={currentIntent?.revision_number}
              selection={selection}
              scope="intent"
              busy={restoreIntent.isPending}
              onSelect={(next) => {
                setMessage(null)
                setSelection(next)
              }}
              onRestore={(row) => {
                if (!currentIntent) return
                setMessage(null)
                restoreIntent.mutate(
                  {
                    profileId: intent.career_profile_id,
                    intentId: intent.search_intent_id,
                    revisionId: row.id,
                    expected: currentIntent.revision_number,
                  },
                  {
                    onSuccess: (result) =>
                      setMessage(
                        result.created
                          ? `Restored revision ${row.number} as revision ${result.intent.current_revision?.revision_number}.`
                          : 'That revision is identical to the current one; nothing was created.',
                      ),
                  },
                )
              }}
            />
          )}
          {selection?.scope === 'intent' && selectedIntent && (
            <Detail onClose={() => setSelection(null)}>
              {selection.mode === 'view' ? (
                <pre className="max-h-80 overflow-auto text-xs whitespace-pre-wrap">
                  {JSON.stringify(selectedIntent.definition, null, 2)}
                </pre>
              ) : (
                <Differences before={selectedIntent.definition} after={currentIntent?.definition} />
              )}
            </Detail>
          )}
        </Card>
      )}
    </div>
  )
}
