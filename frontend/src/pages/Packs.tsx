import { Card } from '@/components/Card'
import { Button } from '@/components/ui/button'
import { describeApiError } from '@/api/errors'
import { usePackActions, usePacks, type Pack } from '@/features/packs/queries'

/** One pack: what it holds, whether it is on, and the button that changes that. */
function PackCard({ pack }: { pack: Pack }) {
  const { setActive } = usePackActions()
  const busy = setActive.isPending && setActive.variables?.packKey === pack.key
  return (
    <Card
      title={pack.name}
      hint={`${pack.role_family_count} role families · ${pack.sector_count} sectors`}
      actions={
        <div className="flex items-center gap-3">
          <span className="text-xs font-medium text-ink-2">{pack.active ? 'On' : 'Off'}</span>
          <Button
            type="button"
            size="sm"
            variant={pack.active ? 'outline' : 'default'}
            disabled={busy}
            onClick={() => setActive.mutate({ packKey: pack.key, active: !pack.active })}
          >
            {pack.active ? 'Switch off' : 'Switch on'}
          </Button>
        </div>
      }
    >
      <p className="text-sm text-ink-2">{pack.description}</p>
      {setActive.isError && setActive.variables?.packKey === pack.key && (
        <p role="alert" className="mt-2 text-sm text-bad">
          {describeApiError(setActive.error).message}
        </p>
      )}
    </Card>
  )
}

/**
 * Packs: ready-made vocabularies for fields of work. Each lists the role families and sectors of a
 * field. Switch on the ones you search in; their terms are then offered in your search intent and
 * to the AI that reads job postings. Switching a pack off deletes nothing: saved searches and
 * history keep working.
 */
export function Packs() {
  const { data, isPending, isError, refetch } = usePacks()
  if (isPending) return <p className="px-4 sm:px-6 py-6 text-ink-3">Loading…</p>
  if (isError)
    return (
      <div role="alert" className="flex items-center gap-3 px-4 sm:px-6 py-6 text-bad">
        Could not load the packs.
        <Button variant="outline" size="sm" onClick={() => void refetch()}>
          Try again
        </Button>
      </div>
    )
  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-4 px-4 sm:px-6 py-6">
      <p className="text-sm text-ink-2">
        A pack is a ready-made list of role families and sectors for one field of work. Switch on
        the fields you search in; you can use several at once. Nothing is deleted when you switch a
        pack off: your saved searches and history keep working, and jobs already analysed are not
        analysed again. Prefer to start from scratch? Leave every pack off and add your own terms in
        Vocabulary.
      </p>
      {data.packs.map((pack) => (
        <PackCard key={pack.key} pack={pack} />
      ))}
    </div>
  )
}
