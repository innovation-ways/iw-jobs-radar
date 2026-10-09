import { Plus } from 'lucide-react'
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { AddJobBoardForm } from './AddJobBoardForm'
import { CataloguePanel } from './CataloguePanel'
import {
  useCatalogue,
  useJobBoardActions,
  useSourceActions,
  useSourceScope,
  type CatalogueEntryRead,
  type CollectionRunRead,
  type SourceRead,
} from './queries'
import { JobBoardsTable } from './JobBoardsTable'
import { ScopeNote } from './ScopeNote'

/**
 * The "Job boards" block of the Sources screen: boards that publish the jobs of many companies.
 * The owner adds one from a short catalogue (entering a key where needed), sees what it would keep
 * before saving, and switches boards on and off like company boards.
 *
 * @param sources the job board sources
 * @param loading true while the list is loading
 * @param activeRun the run in progress, if any
 * @param busy true while a run is being started or is in progress
 * @param onRun starts a manual run of one board
 */
export function JobBoardsSection({
  sources,
  activeRun,
  busy,
  onRun,
}: {
  sources: SourceRead[]
  activeRun: CollectionRunRead | undefined
  busy: boolean
  onRun: (source: SourceRead) => void
}) {
  const catalogue = useCatalogue()
  const scope = useSourceScope()
  const actions = useJobBoardActions()
  const { setEnabled } = useSourceActions()
  const [catalogueOpen, setCatalogueOpen] = useState(false)
  const [chosen, setChosen] = useState<CatalogueEntryRead | null>(null)
  const [added, setAdded] = useState<string | null>(null)

  function close() {
    setCatalogueOpen(false)
    setChosen(null)
  }

  return (
    <section aria-labelledby="job-boards" className="rounded-lg border border-line bg-surface">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3">
        <h2 id="job-boards" className="text-sm font-semibold">
          Job boards
        </h2>
        <Button
          variant="outline"
          size="sm"
          aria-expanded={catalogueOpen}
          onClick={() => (catalogueOpen ? close() : setCatalogueOpen(true))}
        >
          <Plus /> Add a job board
        </Button>
      </div>
      <div className="flex flex-col gap-3 px-4 py-3">
        <p className="text-xs text-ink-3">
          Boards publish jobs from many companies. Filters decide which postings are kept.
        </p>
        <ScopeNote />
        {added && (
          <p role="status" className="rounded-md bg-good-bg px-3 py-2 text-sm text-good">
            Added {added}. Run it to collect its jobs.
          </p>
        )}
        {setEnabled.isError && (
          <p role="alert" className="text-sm text-bad">
            {setEnabled.error.message}
          </p>
        )}
        {catalogueOpen && (
          <div className="flex flex-col gap-3">
            {catalogue.isPending && <p className="text-ink-3">Loading the catalogue…</p>}
            {catalogue.isError && (
              <p role="alert" className="text-bad">
                Could not load the catalogue.
              </p>
            )}
            {catalogue.data && <CataloguePanel entries={catalogue.data} onChoose={setChosen} />}
            {chosen && (
              <AddJobBoardForm
                key={chosen.catalogue_key}
                entry={chosen}
                located={scope.data?.configured ?? false}
                actions={actions}
                onCancel={() => setChosen(null)}
                onAdded={(source) => {
                  setAdded(source.display_name)
                  close()
                }}
              />
            )}
          </div>
        )}
      </div>
      {sources.length === 0 ? (
        <p className="border-t border-line px-4 py-6 text-ink-2">
          No job boards yet. Add one to find companies you do not watch yet.
        </p>
      ) : (
        <JobBoardsTable
          sources={sources}
          activeRun={activeRun}
          busy={busy}
          actions={actions}
          onRun={onRun}
          onToggle={(source) =>
            setEnabled.mutate({
              id: source.source_configuration_id,
              version: source.version,
              enabled: !source.enabled,
            })
          }
        />
      )}
    </section>
  )
}
