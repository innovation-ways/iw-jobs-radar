import { Link } from 'react-router'
import { useSourceScope } from './queries'

function countryName(code: string): string {
  try {
    return new Intl.DisplayNames(['en'], { type: 'region' }).of(code) ?? code
  } catch {
    return code
  }
}

const SHOWN = 6

/**
 * Where job boards look for postings. The countries are never typed into a source: they come from
 * the base location in the profile and the regions of the enabled search intents, so this note is
 * read-only and links to where they are changed.
 */
export function ScopeNote() {
  const scope = useSourceScope()
  if (scope.isPending) return <p className="text-xs text-ink-3">Reading your location…</p>
  if (scope.isError || !scope.data) {
    return (
      <p role="alert" className="text-xs text-bad">
        Could not read where your boards should look.
      </p>
    )
  }
  const { configured, country_codes, include_worldwide, any_country } = scope.data
  if (!configured) {
    return (
      <p role="alert" className="rounded-md bg-caution-bg px-3 py-2 text-sm text-caution">
        Set your base location and the regions where you can work remotely in{' '}
        <Link to="/profile" className="underline">
          Profile & intent
        </Link>
        , and enable a search intent. Job boards cannot look for jobs without them.
      </p>
    )
  }
  const names = country_codes.map(countryName)
  const shown = names.slice(0, SHOWN).join(', ')
  const rest = names.length > SHOWN ? ` and ${names.length - SHOWN} more` : ''
  return (
    <p className="text-xs text-ink-2">
      Looking in:{' '}
      <span className="font-medium text-ink">
        {any_country ? 'any country' : `${shown}${rest}`}
        {include_worldwide && !any_country ? ', plus remote work from anywhere' : ''}
      </span>{' '}
      (from your profile and search intents).{' '}
      <Link to="/profile" className="underline">
        Change it in Profile & intent
      </Link>
      .
    </p>
  )
}
