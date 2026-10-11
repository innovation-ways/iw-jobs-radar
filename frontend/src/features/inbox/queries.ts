import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'
import { unwrap } from '@/api/errors'
import type { components } from '@/api/schema'
import { toQuery, type ListOptions } from './listOptions'
import type { OwnerAction } from './undo'

type Schemas = components['schemas']
export type InboxItem = Schemas['InboxItemSummary']
export type InboxDetail = Schemas['InboxItemDetail']
export type InboxCounts = Schemas['InboxCounts']

export type TabKey =
  'unread' | 'updated' | 'set_aside' | 'shortlist' | 'read' | 'ignored' | 'archived' | 'applied'

export interface TabInfo {
  key: TabKey
  label: string
  count: (counts: InboxCounts) => number
  state: string
  shortlisted?: boolean
  /** Whether the section holds the jobs set aside (true) or leaves them out (false), ADR-058. */
  setAside?: boolean
}

/** The sections of the inbox (each maps to a state filter; Shortlist cuts across states). */
export const TABS: TabInfo[] = [
  { key: 'unread', label: 'To review', count: (c) => c.unread, state: 'unread', setAside: false },
  { key: 'updated', label: 'Updated', count: (c) => c.updated_unread, state: 'updated_unread' },
  // Jobs the owner cannot apply for (a hard constraint fired): still there, but out of the way.
  {
    key: 'set_aside',
    label: 'Set aside',
    count: (c) => c.set_aside,
    state: 'unread',
    setAside: true,
  },
  {
    key: 'shortlist',
    label: 'Shortlist',
    count: (c) => c.shortlisted,
    state: 'all',
    shortlisted: true,
  },
  { key: 'read', label: 'Reviewed', count: (c) => c.read, state: 'read' },
  { key: 'ignored', label: 'Ignored', count: (c) => c.ignored, state: 'ignored' },
  { key: 'archived', label: 'Archived', count: (c) => c.archived, state: 'archived' },
  { key: 'applied', label: 'Applied', count: (c) => c.applied, state: 'applied' },
]

const PAGE_SIZE = 25

interface ListParams {
  tab: TabKey
  search: string
  intentId: number | null
  /** Sort order and filters chosen by the owner. */
  options: ListOptions
  /** False until the intent is known, so the first request already carries it. */
  enabled?: boolean
}

/** The inbox list for a section, loaded page by page with the API's cursor. */
export function useInboxList({ tab, search, intentId, options, enabled = true }: ListParams) {
  const info = TABS.find((t) => t.key === tab)!
  const query = useInfiniteQuery({
    queryKey: ['inbox', 'list', tab, search, intentId, options],
    enabled,
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      unwrap(
        api.GET('/api/v1/inbox', {
          params: {
            query: {
              state: info.state,
              ...(info.shortlisted ? { shortlisted: true } : {}),
              ...(info.setAside !== undefined ? { set_aside: info.setAside } : {}),
              ...(search ? { q: search } : {}),
              ...(intentId !== null ? { search_intent_id: intentId } : {}),
              // "first seen within" is counted from the moment the page is requested.
              ...toQuery(options, new Date()),
              limit: PAGE_SIZE,
              ...(pageParam ? { cursor: pageParam } : {}),
            },
          },
        }),
      ),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  })
  const pages = query.data?.pages ?? []
  return {
    ...query,
    items: pages.flatMap((page) => page.items),
    counts: pages.at(-1)?.counts,
  }
}

/** One item with its job text, evidence and history. */
export function useInboxDetail(itemId: number | null, intentId: number | null) {
  return useQuery({
    queryKey: ['inbox', 'detail', itemId, intentId],
    enabled: itemId !== null,
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/inbox/{job_inbox_item_id}', {
          params: {
            path: { job_inbox_item_id: itemId! },
            ...(intentId !== null ? { query: { search_intent_id: intentId } } : {}),
          },
        }),
      ),
  })
}

/** Owner actions on inbox items and decisions on possible duplicates. */
export function useInboxActions(intentId: number | null) {
  const queryClient = useQueryClient()
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['inbox'] })

  const act = useMutation({
    mutationFn: (input: { itemId: number; action: OwnerAction; version: number }) =>
      unwrap(
        api.POST('/api/v1/inbox/{job_inbox_item_id}/actions', {
          params: {
            path: { job_inbox_item_id: input.itemId },
            query: { ...(intentId !== null ? { search_intent_id: intentId } : {}) },
          },
          body: { action: input.action, expected_version: input.version },
        }),
      ),
    // Refresh on failure too: a conflict means what is on screen is out of date.
    onSettled: refresh,
  })
  const decideLink = useMutation({
    mutationFn: (input: { linkId: number; decision: 'confirm' | 'reject' }) =>
      unwrap(
        api.POST(
          input.decision === 'confirm'
            ? '/api/v1/opportunity-links/{job_opportunity_link_id}/confirm'
            : '/api/v1/opportunity-links/{job_opportunity_link_id}/reject',
          { params: { path: { job_opportunity_link_id: input.linkId } } },
        ),
      ),
    onSettled: refresh,
  })
  return { act, decideLink }
}
