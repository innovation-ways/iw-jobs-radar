import { Plus, Trash2 } from 'lucide-react'
import { Card } from '@/components/Card'
import { Button } from '@/components/ui/button'
import { MAX_DIRECTIONS, MAX_DIRECTION_LABEL, MAX_DIRECTION_TEXT, type ProfileForm } from './form'

type Directions = ProfileForm['directions']

const field = 'rounded-md border border-line-strong bg-surface px-2.5 py-1.5 text-sm'

interface Props {
  directions: Directions
  onChange: (directions: Directions) => void
}

/**
 * The owner's career directions: short texts in their own words about what they look for, judged
 * by the local model against every new job (ADR-057). The best fit among the enabled directions
 * counts. Props: the current list and a change callback; saving is done by the profile panel.
 */
export function DirectionsEditor({ directions, onChange }: Props) {
  const full = directions.length >= MAX_DIRECTIONS
  const patch = (index: number, change: Partial<Directions[number]>) =>
    onChange(directions.map((item, i) => (i === index ? { ...item, ...change } : item)))

  return (
    <Card
      title="Career directions"
      hint="What you are looking for, in your own words. The local model judges every new job against each enabled direction, and the best fit counts."
      actions={
        <Button
          variant="outline"
          size="sm"
          disabled={full}
          onClick={() => onChange([...directions, { label: '', text: '', enabled: true }])}
        >
          <Plus /> Add a direction
        </Button>
      }
    >
      <p className="mb-3 text-xs text-ink-3">
        Write in English. Only jobs first seen after you save a direction are judged on their own;
        an older job is judged when you ask for it in its detail. Give the dimension a weight in
        your search intent for it to count towards the score.
        {full && ` You can have at most ${MAX_DIRECTIONS} directions.`}
      </p>
      {directions.length === 0 ? (
        <p className="text-sm text-ink-2">
          No directions yet. Example: “I work as a billing SME and look for telecom roles that fit
          my skills; I am also moving from software engineering into AI engineering, backed by my
          open-source work.”
        </p>
      ) : (
        <ul className="flex flex-col gap-3">
          {directions.map((item, index) => (
            <li
              key={index}
              className="grid gap-2 rounded-md border border-line p-3 sm:grid-cols-[1fr_auto]"
            >
              <label className="flex flex-col gap-1 text-xs text-ink-2">
                Label
                <input
                  aria-label="Direction label"
                  className={field}
                  maxLength={MAX_DIRECTION_LABEL}
                  value={item.label}
                  onChange={(event) => patch(index, { label: event.target.value })}
                />
              </label>
              <label className="flex items-end gap-2 pb-1.5 text-sm">
                <input
                  type="checkbox"
                  checked={item.enabled}
                  onChange={(event) => patch(index, { enabled: event.target.checked })}
                  aria-label="Judge new jobs against this"
                />
                Judge new jobs against this
              </label>
              <label className="flex flex-col gap-1 text-xs text-ink-2 sm:col-span-2">
                Text
                <textarea
                  aria-label="Direction text"
                  className={`${field} min-h-24`}
                  value={item.text}
                  onChange={(event) => patch(index, { text: event.target.value })}
                />
                <span className="text-right tabular-nums">
                  {item.text.length.toLocaleString('en')} /{' '}
                  {MAX_DIRECTION_TEXT.toLocaleString('en')}
                </span>
              </label>
              <div className="sm:col-span-2">
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={`Remove direction ${item.label || index + 1}`}
                  onClick={() => onChange(directions.filter((_, i) => i !== index))}
                >
                  <Trash2 /> Remove direction
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}
