import { describe, expect, it } from 'vitest'
import { undoPlan } from './undo'

describe('undoPlan', () => {
  it('takes back opening by marking unread', () => {
    expect(undoPlan('open', 'unread')).toEqual(['mark_unread'])
  })

  it('takes back ignore, archive and an application with restore', () => {
    expect(undoPlan('ignore', 'read')).toEqual(['restore'])
    expect(undoPlan('archive', 'read')).toEqual(['restore'])
    expect(undoPlan('record_application', 'read')).toEqual(['restore'])
  })

  it('goes back to unread when the item was unread before (restore returns to read)', () => {
    expect(undoPlan('ignore', 'unread')).toEqual(['restore', 'mark_unread'])
    expect(undoPlan('archive', 'updated_unread')).toEqual(['restore', 'mark_unread'])
    expect(undoPlan('record_application', 'unread')).toEqual(['restore', 'mark_unread'])
  })

  it('takes back shortlisting both ways', () => {
    expect(undoPlan('shortlist', 'read')).toEqual(['unshortlist'])
    expect(undoPlan('unshortlist', 'read')).toEqual(['shortlist'])
  })

  it('has nothing to undo for mark unread and restore', () => {
    expect(undoPlan('mark_unread', 'read')).toEqual([])
    expect(undoPlan('restore', 'ignored')).toEqual([])
  })
})
