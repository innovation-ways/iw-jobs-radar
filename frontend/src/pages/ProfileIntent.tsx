import { useCallback, useState } from 'react'
import { Button } from '@/components/ui/button'
import { defaultIntentDefinition } from '@/features/intent/defaults'
import { IntentPanel } from '@/features/intent/IntentPanel'
import { HistoryPanel } from '@/features/history/HistoryPanel'
import { ProfilePanel } from '@/features/profile/ProfilePanel'
import {
  useIntents,
  useProfileActions,
  useProfiles,
  useTaxonomy,
  type ProfileRead,
} from '@/features/profile/queries'
import { cn } from '@/lib/utils'

type Tab = 'profile' | 'intent' | 'weights' | 'history'

const TABS: { id: Tab; label: string }[] = [
  { id: 'profile', label: 'Profile' },
  { id: 'intent', label: 'Search intent' },
  { id: 'weights', label: 'Scoring weights' },
  { id: 'history', label: 'History' },
]

const field = 'rounded-md border border-line-strong bg-surface px-2.5 py-1.5 text-sm'
const UNSAVED = 'You have unsaved changes that will be lost. Continue?'

function NewProfileForm({
  initialName,
  onCreated,
  onCancel,
}: {
  initialName: string
  onCreated: (profile: ProfileRead) => void
  onCancel?: () => void
}) {
  const { createProfile } = useProfileActions()
  const [name, setName] = useState(initialName)
  return (
    <form
      className="flex flex-wrap items-end gap-2.5"
      onSubmit={(event) => {
        event.preventDefault()
        if (name.trim()) createProfile.mutate(name.trim(), { onSuccess: onCreated })
      }}
    >
      <label className="flex flex-col gap-1 text-xs text-ink-2">
        Profile name
        <input
          className={field}
          value={name}
          maxLength={120}
          onChange={(event) => setName(event.target.value)}
        />
      </label>
      <Button type="submit" disabled={!name.trim() || createProfile.isPending}>
        Create profile
      </Button>
      {onCancel && (
        <Button type="button" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
      )}
      {createProfile.isError && (
        <p role="alert" className="basis-full text-sm text-bad">
          {createProfile.error.message}
        </p>
      )}
    </form>
  )
}

/**
 * Profile & intent: the career profile, the search intent, the scoring weights and the revision
 * history. Unsaved edits are kept per section and the owner is asked before they would be lost.
 */
export function ProfileIntent() {
  const profiles = useProfiles()
  const taxonomy = useTaxonomy()
  const { createIntent } = useProfileActions()
  const [profileId, setProfileId] = useState<number | null>(null)
  const [intentId, setIntentId] = useState<number | null>(null)
  const [tab, setTab] = useState<Tab>('profile')
  const [creating, setCreating] = useState(false)
  const [dirty, setDirty] = useState({ profile: false, intent: false })

  const profile =
    profiles.data?.find((p) => p.career_profile_id === profileId) ?? profiles.data?.[0] ?? null
  const intents = useIntents(profile?.career_profile_id)
  const intent =
    intents.data?.find((i) => i.search_intent_id === intentId) ?? intents.data?.[0] ?? null
  const anyDirty = dirty.profile || dirty.intent
  // Stable callbacks that change state only when the flag really changes (no render loops).
  const setProfileDirty = useCallback(
    (value: boolean) =>
      setDirty((previous) =>
        previous.profile === value ? previous : { ...previous, profile: value },
      ),
    [],
  )
  const setIntentDirty = useCallback(
    (value: boolean) =>
      setDirty((previous) =>
        previous.intent === value ? previous : { ...previous, intent: value },
      ),
    [],
  )
  const confirmLoss = () => !anyDirty || window.confirm(UNSAVED)

  if (profiles.isPending) return <p className="px-6 py-8 text-ink-3">Loading…</p>
  if (profiles.isError) {
    return (
      <div role="alert" className="mx-auto flex max-w-3xl items-center gap-3 px-6 py-8 text-bad">
        Could not load your profiles.
        <Button variant="outline" size="sm" onClick={() => void profiles.refetch()}>
          Try again
        </Button>
      </div>
    )
  }
  if (!profile) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-8">
        <div className="rounded-lg border border-line bg-surface p-5">
          <h2 className="text-sm font-semibold">Create your first profile</h2>
          <p className="mt-1 mb-4 text-sm text-ink-2">
            Your career profile holds the facts about you. Everything stays on this machine.
          </p>
          <NewProfileForm
            initialName="My profile"
            onCreated={(created) => setProfileId(created.career_profile_id)}
          />
        </div>
      </div>
    )
  }

  const hasRevision = profile.current_revision !== null

  function createDefaultIntent() {
    if (!taxonomy.data || !profile) return
    createIntent.mutate(
      {
        profileId: profile.career_profile_id,
        definition: defaultIntentDefinition(taxonomy.data, profile),
      },
      {
        onSuccess: (created) => {
          setIntentId(created.search_intent_id)
          setTab('intent')
        },
      },
    )
  }

  const intentSections = tab === 'intent' || tab === 'weights'

  return (
    <div className="flex min-h-full flex-col">
      <div className="border-b border-line bg-surface px-6 py-3">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-xs text-ink-2">
            Career profile
            <select
              className={field}
              value={profile.career_profile_id}
              onChange={(event) => {
                if (!confirmLoss()) return
                setProfileId(Number(event.target.value))
                setIntentId(null)
              }}
            >
              {profiles.data.map((p) => (
                <option key={p.career_profile_id} value={p.career_profile_id}>
                  {p.title} ·{' '}
                  {p.current_revision
                    ? `revision ${p.current_revision.revision_number}`
                    : 'no revision yet'}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs text-ink-2">
            Search intent
            <select
              className={field}
              disabled={!intents.data?.length}
              value={intent?.search_intent_id ?? ''}
              onChange={(event) => {
                if (!confirmLoss()) return
                setIntentId(Number(event.target.value))
              }}
            >
              {intents.data?.length ? (
                intents.data.map((i) => (
                  <option key={i.search_intent_id} value={i.search_intent_id}>
                    {i.title} · revision {i.current_revision?.revision_number}
                  </option>
                ))
              ) : (
                <option value="">No intent yet</option>
              )}
            </select>
          </label>
          <Button variant="outline" size="sm" onClick={() => setCreating((open) => !open)}>
            + New profile
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={!hasRevision || !taxonomy.data || createIntent.isPending}
            onClick={createDefaultIntent}
          >
            + New intent
          </Button>
        </div>
        {creating && (
          <div className="mt-3">
            <NewProfileForm
              initialName=""
              onCancel={() => setCreating(false)}
              onCreated={(created) => {
                setProfileId(created.career_profile_id)
                setIntentId(null)
                setCreating(false)
                setTab('profile')
              }}
            />
          </div>
        )}
        <div role="tablist" aria-label="Profile and intent sections" className="mt-3 flex gap-1">
          {TABS.map((item) => (
            <button
              key={item.id}
              role="tab"
              type="button"
              aria-selected={tab === item.id}
              aria-controls={`panel-${item.id}`}
              onClick={() => setTab(item.id)}
              className={cn(
                'rounded-md px-3 py-1.5 text-sm font-medium',
                tab === item.id ? 'bg-brand-soft text-brand-text' : 'text-ink-2 hover:bg-surface-2',
              )}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>

      <div className="mx-auto w-full max-w-5xl flex-1 px-6 py-5">
        {/* Panels stay mounted (hidden) so unsaved edits survive switching sections. */}
        <div role="tabpanel" id="panel-profile" hidden={tab !== 'profile'}>
          <ProfilePanel
            key={profile.career_profile_id}
            profile={profile}
            onDirtyChange={setProfileDirty}
          />
        </div>
        <div role="tabpanel" id="panel-intent" hidden={!intentSections}>
          {intent?.current_revision && taxonomy.data ? (
            <IntentPanel
              key={intent.search_intent_id}
              intent={intent}
              taxonomy={taxonomy.data}
              section={tab === 'weights' ? 'weights' : 'intent'}
              onDirtyChange={setIntentDirty}
            />
          ) : (
            intentSections && (
              <div className="rounded-lg border border-line bg-surface p-5">
                <h2 className="text-sm font-semibold">No search intent yet</h2>
                {hasRevision ? (
                  <>
                    <p className="mt-1 mb-3 text-sm text-ink-2">
                      An intent says what you are looking for. It starts neutral and you adjust it.
                    </p>
                    <Button
                      onClick={createDefaultIntent}
                      disabled={!taxonomy.data || createIntent.isPending}
                    >
                      Create search intent
                    </Button>
                  </>
                ) : (
                  <p className="mt-1 text-sm text-ink-2">
                    Save the profile first: the intent starts from your base place and languages.
                  </p>
                )}
                {createIntent.isError && (
                  <p role="alert" className="mt-2 text-sm text-bad">
                    {createIntent.error.message}
                  </p>
                )}
              </div>
            )
          )}
        </div>
        {tab === 'history' && (
          <div role="tabpanel" id="panel-history">
            <HistoryPanel profile={profile} intent={intent} />
          </div>
        )}
      </div>
    </div>
  )
}
