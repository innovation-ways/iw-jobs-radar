import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { Button } from '@/components/ui/button'
import { JobDetail } from '@/features/inbox/JobDetail'
import { JobRow } from '@/features/inbox/JobRow'
import {
  DEFAULT_OPTIONS,
  FIT_LABELS,
  hasActiveFilters,
  parseFit,
  parseSort,
  SEEN_LABELS,
  SORT_LABELS,
  type FitFilter,
  type ListOptions,
  type SeenFilter,
} from '@/features/inbox/listOptions'
import {
  TABS,
  useInboxActions,
  useInboxDetail,
  useInboxList,
  type InboxItem,
  type TabKey,
} from '@/features/inbox/queries'
import { useOutletContext } from 'react-router'
import type { ShellContext } from '@/components/AppShell'
import { createPortal } from 'react-dom'
import { ShortcutsHelp } from '@/features/inbox/ShortcutsHelp'
import { ACTION_MESSAGES, undoPlan, type InboxState, type OwnerAction } from '@/features/inbox/undo'
import { useShortcuts } from '@/features/inbox/useShortcuts'
import { useIntents, useProfiles } from '@/features/profile/queries'
import { cn } from '@/lib/utils'

const DENSITY_KEY = 'jobs-radar:inbox-density'
const INTENT_KEY = 'jobs-radar:inbox-intent'
const SORT_KEY = 'jobs-radar:inbox-sort'
const TOAST_MS = 7000
const SEARCH_DELAY_MS = 300

type Density = 'comfortable' | 'compact'

function readStored(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null // storage can be blocked; the screen works without remembering
  }
}

function store(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch {
    // ignored: remembering a preference is a convenience only
  }
}

interface LastAction {
  itemId: number
  action: OwnerAction
  previous: InboxState
  version: number
}

/**
 * The inbox: a keyboard-first list of job cards beside a detail panel. Scores come from the chosen
 * search intent; jobs without a score are listed as "not evaluated". Every action can be undone.
 */
export function Inbox() {
  const [tab, setTab] = useState<TabKey>('unread')
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [density, setDensity] = useState<Density>(() =>
    readStored(DENSITY_KEY) === 'compact' ? 'compact' : 'comfortable',
  )
  // A link from the pipeline panel can open the inbox already filtered (``?fit=unscored``).
  const [searchParams] = useSearchParams()
  const [options, setOptions] = useState<ListOptions>(() => ({
    ...DEFAULT_OPTIONS,
    fit: parseFit(searchParams.get('fit')),
    sort: parseSort(readStored(SORT_KEY)),
  }))
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [helpOpen, setHelpOpen] = useState(false)
  // The "?" button lives in the application header next to the theme toggle (a slot of AppShell).
  const headerSlot = useOutletContext<ShellContext | undefined>()?.headerSlot ?? null
  const [toast, setToast] = useState<{ message: string; undo: LastAction | null } | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [intentChoice, setIntentChoice] = useState<number | null>(
    () => Number(readStored(INTENT_KEY)) || null,
  )
  const searchRef = useRef<HTMLInputElement>(null)

  const profiles = useProfiles()
  const profileId = profiles.data?.[0]?.career_profile_id
  const intents = useIntents(profileId)
  const intentList = intents.data ?? []
  const intentId =
    intentList.find((i) => i.search_intent_id === intentChoice)?.search_intent_id ??
    intentList[0]?.search_intent_id ??
    null
  const waitingForIntents = profiles.isPending || (profileId !== undefined && intents.isPending)

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search.trim()), SEARCH_DELAY_MS)
    return () => clearTimeout(timer)
  }, [search])

  const list = useInboxList({
    tab,
    search: debouncedSearch,
    intentId,
    options,
    enabled: !waitingForIntents,
  })
  const items = list.items
  // Neighbours of the job last acted on, in order of preference (next, then previous): when that
  // job leaves the list, the selection moves to the first of them still listed, not to the top.
  const [fallbackIds, setFallbackIds] = useState<number[]>([])
  const byId = (id: number | null) => items.find((i) => i.job_inbox_item_id === id)
  const selected = byId(selectedId) ?? fallbackIds.map(byId).find(Boolean) ?? items[0] ?? null
  const detail = useInboxDetail(selected?.job_inbox_item_id ?? null, intentId)
  const { act, decideLink } = useInboxActions(intentId)

  useEffect(() => {
    if (!toast) return
    const timer = setTimeout(() => setToast(null), TOAST_MS)
    return () => clearTimeout(timer)
  }, [toast])

  /** Perform one action on an item, remembering how to take it back. */
  const perform = useCallback(
    async (item: InboxItem, action: OwnerAction) => {
      setActionError(null)
      const index = items.findIndex((i) => i.job_inbox_item_id === item.job_inbox_item_id)
      setSelectedId(item.job_inbox_item_id)
      setFallbackIds(
        [items[index + 1], items[index - 1]].filter(Boolean).map((i) => i.job_inbox_item_id),
      )
      try {
        const result = await act.mutateAsync({
          itemId: item.job_inbox_item_id,
          action,
          version: item.version,
        })
        const undo = undoPlan(action, item.state)
        setToast({
          message: ACTION_MESSAGES[action],
          undo: undo.length
            ? {
                itemId: item.job_inbox_item_id,
                action,
                previous: item.state,
                version: result.item.version,
              }
            : null,
        })
      } catch (error) {
        setActionError(error instanceof Error ? error.message : 'The action failed.')
      }
    },
    [act, items],
  )

  const undo = useCallback(async () => {
    const last = toast?.undo
    if (!last) return
    setToast(null)
    setActionError(null)
    let version = last.version
    try {
      for (const action of undoPlan(last.action, last.previous)) {
        const result = await act.mutateAsync({ itemId: last.itemId, action, version })
        version = result.item.version
      }
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'The action could not be undone.')
    }
  }, [act, toast])

  const move = useCallback(
    (delta: number) => {
      if (!items.length) return
      const index = items.findIndex((i) => i.job_inbox_item_id === selected?.job_inbox_item_id)
      const next = items[Math.min(items.length - 1, Math.max(0, index + delta))]
      setSelectedId(next.job_inbox_item_id)
    },
    [items, selected],
  )

  const on = useCallback(
    (action: OwnerAction) => () => {
      if (!selected) return
      if (action === 'shortlist')
        return void perform(selected, selected.is_shortlisted ? 'unshortlist' : 'shortlist')
      return void perform(selected, action)
    },
    [perform, selected],
  )

  const shortcuts = useMemo(
    () => ({
      j: () => move(1),
      k: () => move(-1),
      s: on('shortlist'),
      i: on('ignore'),
      a: on('archive'),
      m: () => {
        // "Mark as read" only exists for unread jobs; elsewhere the key does nothing.
        if (selected?.state === 'unread' || selected?.state === 'updated_unread') on('open')()
      },
      o: () => {
        const url = detail.data?.apply_url
        // Opening the page does not change the job (same as the link): noopener keeps the tab isolated.
        if (url) window.open(url, '_blank', 'noopener,noreferrer')
      },
      ArrowDown: () => move(1),
      ArrowUp: () => move(-1),
      u: on('mark_unread'),
      r: on('restore'),
      z: () => void undo(),
      '?': () => setHelpOpen(true),
      '/': () => searchRef.current?.focus(),
    }),
    [move, on, undo, selected, detail.data],
  )
  useShortcuts(shortcuts, !helpOpen)

  const counts = list.counts
  const emptyInbox = counts?.total === 0
  const changeDensity = (value: Density) => {
    setDensity(value)
    store(DENSITY_KEY, value)
  }

  return (
    <div
      data-testid="inbox-root"
      data-density={density}
      className="group/inbox grid h-full min-h-0 grid-cols-[minmax(340px,1fr)_580px]"
    >
      <div className="flex min-h-0 min-w-0 flex-col border-r border-line">
        <div
          role="tablist"
          aria-label="Inbox sections"
          className="flex gap-0.5 border-b border-line bg-surface px-3.5 pt-2"
        >
          {TABS.map((info) => (
            <button
              key={info.key}
              role="tab"
              type="button"
              aria-selected={tab === info.key}
              onClick={() => setTab(info.key)}
              className={cn(
                'flex flex-col items-center border-b-2 px-2.5 py-1.5 leading-tight',
                tab === info.key
                  ? 'border-brand font-semibold text-ink'
                  : 'border-transparent text-ink-2 hover:text-ink',
              )}
            >
              {info.label}
              <span className="text-xs text-ink-3 tabular-nums">
                {counts ? info.count(counts) : ''}
              </span>
            </button>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-2.5 border-b border-line bg-surface px-3.5 py-2.5">
          <input
            ref={searchRef}
            type="search"
            aria-label="Search jobs"
            placeholder="Search title, company, technology…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            className="min-w-48 flex-1 rounded-md bg-surface-2 px-2.5 py-1.5 text-sm"
          />
          <label className="flex items-center gap-1.5 text-xs text-ink-2">
            Sort by
            <select
              value={options.sort}
              onChange={(event) => {
                const sort = parseSort(event.target.value)
                setOptions({ ...options, sort })
                store(SORT_KEY, sort)
              }}
              className="rounded-md border border-line-strong bg-surface px-2 py-1 text-sm text-ink"
            >
              {Object.entries(SORT_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-1.5 text-xs text-ink-2">
            Fit
            <select
              value={options.fit}
              onChange={(event) => setOptions({ ...options, fit: event.target.value as FitFilter })}
              className="rounded-md border border-line-strong bg-surface px-2 py-1 text-sm text-ink"
            >
              {Object.entries(FIT_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-1.5 text-xs text-ink-2">
            First seen
            <select
              value={options.seen}
              onChange={(event) =>
                setOptions({ ...options, seen: event.target.value as SeenFilter })
              }
              className="rounded-md border border-line-strong bg-surface px-2 py-1 text-sm text-ink"
            >
              {Object.entries(SEEN_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          {hasActiveFilters(options) && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setOptions({ ...DEFAULT_OPTIONS, sort: options.sort })}
            >
              Clear filters
            </Button>
          )}
          {intentList.length > 1 && (
            <label className="flex items-center gap-1.5 text-xs text-ink-2">
              Scored for
              <select
                value={intentId ?? ''}
                onChange={(event) => {
                  setIntentChoice(Number(event.target.value))
                  store(INTENT_KEY, event.target.value)
                }}
                className="rounded-md border border-line-strong bg-surface px-2 py-1 text-sm text-ink"
              >
                {intentList.map((intent) => (
                  <option key={intent.search_intent_id} value={intent.search_intent_id}>
                    {intent.title}
                  </option>
                ))}
              </select>
            </label>
          )}
          <div
            role="group"
            aria-label="Density"
            className="inline-flex rounded-md border border-line-strong"
          >
            {(['comfortable', 'compact'] as const).map((value) => (
              <button
                key={value}
                type="button"
                aria-pressed={density === value}
                onClick={() => changeDensity(value)}
                className={cn(
                  'border-r border-line-strong px-2.5 py-1 text-xs font-medium capitalize last:border-r-0',
                  density === value
                    ? 'bg-brand-soft text-brand-text'
                    : 'text-ink-2 hover:bg-surface-2',
                )}
              >
                {value === 'comfortable' ? 'Comfortable' : 'Compact'}
              </button>
            ))}
          </div>
        </div>

        {!waitingForIntents && intentId === null && (
          <p className="border-b border-line bg-brand-soft px-3.5 py-2 text-sm text-brand-text">
            Create a search intent in{' '}
            <Link to="/profile" className="underline">
              Profile &amp; intent
            </Link>{' '}
            to score these jobs. Until then they are listed as not evaluated.
          </p>
        )}
        {actionError && (
          <p role="alert" className="border-b border-line bg-bad-bg px-3.5 py-2 text-sm text-bad">
            {actionError}
          </p>
        )}

        <div
          role="listbox"
          aria-label="Jobs"
          className="flex flex-1 flex-col gap-2 overflow-y-auto bg-bg px-3 py-2.5 group-data-[density=compact]/inbox:gap-1.5"
        >
          {list.isPending && <p className="py-6 text-center text-ink-3">Loading…</p>}
          {list.isError && (
            <div role="alert" className="flex items-center justify-center gap-3 py-6 text-bad">
              Could not load the inbox.
              <Button variant="outline" size="sm" onClick={() => void list.refetch()}>
                Try again
              </Button>
            </div>
          )}
          {!list.isPending &&
            !list.isError &&
            items.length === 0 &&
            (emptyInbox ? (
              <p className="px-4 py-7 text-center text-sm text-ink-3">
                No jobs yet. Add a board and run it in{' '}
                <Link to="/sources" className="underline">
                  Sources
                </Link>
                , then come back.
              </p>
            ) : (
              <p className="px-4 py-7 text-center text-sm text-ink-3">Nothing here.</p>
            ))}
          {items.map((item) => (
            <JobRow
              key={item.job_inbox_item_id}
              item={item}
              selected={item.job_inbox_item_id === selected?.job_inbox_item_id}
              onSelect={() => setSelectedId(item.job_inbox_item_id)}
              floor={list.setAsideBelowFit}
            />
          ))}
          {list.hasNextPage && (
            <Button
              variant="outline"
              disabled={list.isFetchingNextPage}
              onClick={() => void list.fetchNextPage()}
            >
              {list.isFetchingNextPage ? 'Loading…' : 'Show more'}
            </Button>
          )}
        </div>
      </div>

      <div className="min-h-0 overflow-y-auto bg-surface" aria-live="polite">
        {selected && detail.data && (
          <JobDetail
            detail={detail.data}
            busy={act.isPending}
            onAction={(action) => void perform(selected, action)}
            onLinkDecision={(linkId, decision) => decideLink.mutate({ linkId, decision })}
          />
        )}
        {selected && detail.isPending && <p className="p-5 text-ink-3">Loading…</p>}
        {selected && detail.isError && (
          <p role="alert" className="p-5 text-bad">
            Could not load this job.
          </p>
        )}
      </div>

      {toast && (
        <div
          role="status"
          className="fixed bottom-6 left-1/2 z-20 flex -translate-x-1/2 items-center gap-3.5 rounded-lg bg-ink px-3.5 py-2 text-[13px] text-bg shadow-lg"
        >
          <span>{toast.message}</span>
          {toast.undo && (
            <button type="button" onClick={() => void undo()} className="font-bold underline">
              Undo <kbd className="text-[11px]">z</kbd>
            </button>
          )}
        </div>
      )}
      {headerSlot &&
        createPortal(
          <Button
            variant="ghost"
            size="sm"
            aria-label="Keyboard shortcuts"
            onClick={() => setHelpOpen(true)}
          >
            <kbd>?</kbd>
          </Button>,
          headerSlot,
        )}
      {helpOpen && <ShortcutsHelp onClose={() => setHelpOpen(false)} />}
    </div>
  )
}
