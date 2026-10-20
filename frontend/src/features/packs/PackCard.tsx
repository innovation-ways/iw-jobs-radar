import { Card } from '@/components/Card'
import { Button } from '@/components/ui/button'
import { describeApiError } from '@/api/errors'
import { usePackActions, type Pack } from './queries'

/** One pack: what it holds, whether it is on, and the button that changes that. */
export function PackCard({ pack }: { pack: Pack }) {
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
