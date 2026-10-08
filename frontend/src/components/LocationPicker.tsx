import { useQuery } from '@tanstack/react-query'
import { useId, useState } from 'react'
import { searchPlaces, type PlaceRead } from '@/features/profile/queries'

interface Props {
  label: string
  /** The place currently chosen, shown in the field. */
  value: string
  onSelect: (place: PlaceRead) => void
}

const MIN_CHARACTERS = 2

/**
 * Autocomplete over the offline city gazetteer. Choosing a result reports the city with its
 * coordinates and time zone, so the owner never types latitude or longitude.
 */
export function LocationPicker({ label, value, onSelect }: Props) {
  const id = useId()
  const [text, setText] = useState<string | null>(null) // null: show the chosen value
  const [active, setActive] = useState(-1)
  const query = (text ?? '').trim()
  const enabled = query.length >= MIN_CHARACTERS
  const { data: places = [], isFetching } = useQuery({
    queryKey: ['places', query],
    enabled,
    staleTime: Infinity, // the gazetteer is static data
    queryFn: () => searchPlaces(query),
  })
  const open = enabled && text !== null

  function choose(place: PlaceRead) {
    onSelect(place)
    setText(null)
    setActive(-1)
  }

  return (
    <div className="relative">
      <label htmlFor={id} className="text-xs text-ink-2">
        {label}
      </label>
      <input
        id={id}
        role="combobox"
        aria-expanded={open}
        aria-controls={`${id}-list`}
        aria-autocomplete="list"
        aria-activedescendant={active >= 0 ? `${id}-${active}` : undefined}
        autoComplete="off"
        value={text ?? value}
        onChange={(event) => {
          setText(event.target.value)
          setActive(-1)
        }}
        onFocus={(event) => event.target.select()}
        onBlur={() => setText(null)}
        onKeyDown={(event) => {
          if (event.key === 'ArrowDown') {
            event.preventDefault()
            setActive((index) => Math.min(index + 1, places.length - 1))
          } else if (event.key === 'ArrowUp') {
            event.preventDefault()
            setActive((index) => Math.max(index - 1, 0))
          } else if (event.key === 'Enter' && active >= 0 && places[active]) {
            event.preventDefault()
            choose(places[active])
          } else if (event.key === 'Escape') {
            setText(null)
          }
        }}
        className="mt-1 w-full rounded-md border border-line-strong bg-surface px-2.5 py-1.5 text-sm"
      />
      {open && (
        <ul
          id={`${id}-list`}
          role="listbox"
          aria-label={`${label} suggestions`}
          className="absolute z-20 mt-1 max-h-60 w-full overflow-auto rounded-md border border-line bg-surface shadow-lg"
        >
          {places.map((place, index) => (
            <li
              key={`${place.label}-${place.latitude}-${place.longitude}`}
              id={`${id}-${index}`}
              role="option"
              aria-selected={index === active}
              // mousedown (not click) so the selection happens before the field loses focus
              onMouseDown={(event) => {
                event.preventDefault()
                choose(place)
              }}
              className={`cursor-pointer px-2.5 py-1.5 text-sm ${index === active ? 'bg-brand-soft' : 'hover:bg-surface-2'}`}
            >
              {place.label}
              <span className="ml-2 text-xs text-ink-3">{place.timezone}</span>
            </li>
          ))}
          {!isFetching && places.length === 0 && (
            <li className="px-2.5 py-1.5 text-sm text-ink-3">
              No matching city. Only cities above 15,000 inhabitants are known offline.
            </li>
          )}
        </ul>
      )}
    </div>
  )
}
