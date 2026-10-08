import type { components } from '@/api/schema'

export type OwnerAction = components['schemas']['InboxActionRequest']['action']
export type InboxState = components['schemas']['InboxItemSummary']['state']

/**
 * The actions that take back `action`, given the state the item had before it. `restore` returns
 * an item to "read" (LLD section 3), so an item that was unread is marked unread again afterwards.
 */
export function undoPlan(action: OwnerAction, previous: InboxState): OwnerAction[] {
  const wasUnread = previous === 'unread' || previous === 'updated_unread'
  switch (action) {
    case 'open':
      return ['mark_unread']
    case 'ignore':
    case 'archive':
    case 'record_application':
      return wasUnread ? ['restore', 'mark_unread'] : ['restore']
    case 'shortlist':
      return ['unshortlist']
    case 'unshortlist':
      return ['shortlist']
    default:
      return []
  }
}
