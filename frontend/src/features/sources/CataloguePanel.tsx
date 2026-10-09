import { Button } from '@/components/ui/button'
import type { CatalogueEntryRead } from './queries'

/**
 * The job boards that can be added, each with where it looks, what it asks for and whether it
 * needs a free key. A board that is already added shows as such and has no button.
 *
 * @param entries the catalogue
 * @param onChoose called with the board whose form should open
 */
export function CataloguePanel({
  entries,
  onChoose,
}: {
  entries: CatalogueEntryRead[]
  onChoose: (entry: CatalogueEntryRead) => void
}) {
  return (
    <ul
      aria-label="Job board catalogue"
      className="divide-y divide-line rounded-md border border-line"
    >
      {entries.map((entry) => (
        <li key={entry.catalogue_key} className="flex flex-wrap items-center gap-3 px-3.5 py-2.5">
          <div className="min-w-0 flex-1">
            <div className="font-medium">{entry.display_name}</div>
            <div className="text-xs text-ink-2">{entry.coverage_note}</div>
            <div className="text-xs text-ink-3">{entry.terms_note}</div>
          </div>
          <span className="text-xs text-ink-2">
            {entry.requires_credential ? 'Needs a free key' : 'Free, no key'}
          </span>
          {entry.already_added ? (
            <span className="text-xs font-semibold text-good">Added</span>
          ) : (
            <Button size="sm" variant="outline" onClick={() => onChoose(entry)}>
              Add {entry.display_name}
            </Button>
          )}
        </li>
      ))}
    </ul>
  )
}
