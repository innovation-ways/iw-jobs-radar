import { expect, test, type Route } from '@playwright/test'

/**
 * Inbox flow against a stateful in-memory stub of the API (no database, no real network): open a
 * job, shortlist it, ignore it and undo, restore it, mark it applied and undo that.
 */

type State = 'unread' | 'read' | 'updated_unread' | 'ignored' | 'archived' | 'applied'
interface Job {
  id: number
  title: string
  state: State
  shortlisted: boolean
  version: number
  score: number | null
}

const NEXT: Record<string, { from: State[]; to: State }> = {
  open: { from: ['unread', 'updated_unread'], to: 'read' },
  mark_unread: { from: ['read', 'ignored', 'archived', 'applied'], to: 'unread' },
  ignore: { from: ['unread', 'read', 'updated_unread'], to: 'ignored' },
  restore: { from: ['ignored', 'archived', 'applied'], to: 'read' },
  archive: { from: ['unread', 'read', 'updated_unread', 'ignored'], to: 'archived' },
  record_application: { from: ['unread', 'read', 'updated_unread'], to: 'applied' },
}

function createStub() {
  const jobs: Job[] = [
    {
      id: 1,
      title: 'Senior AI Solutions Engineer',
      state: 'unread',
      shortlisted: false,
      version: 1,
      score: 82,
    },
    {
      id: 2,
      title: 'Platform Engineer',
      state: 'unread',
      shortlisted: false,
      version: 1,
      score: 61,
    },
  ]
  const json = (route: Route, body: unknown, status = 200) => route.fulfill({ status, json: body })

  const summary = (job: Job) => ({
    job_inbox_item_id: job.id,
    job_opportunity_id: 100 + job.id,
    job_posting_id: 200 + job.id,
    state: job.state,
    is_shortlisted: job.shortlisted,
    version: job.version,
    title: job.title,
    company_name: 'Northwind Labs',
    locations: ['Remote - EU'],
    first_seen_at: '2026-10-08T10:00:00Z',
    last_seen_at: '2026-10-08T10:00:00Z',
    closed: false,
    evaluated: job.score !== null,
    evaluation:
      job.score === null
        ? null
        : {
            match_evaluation_id: 900 + job.id,
            policy_version: 'matching-v1.1',
            fit_score: job.score,
            fit_band: job.score >= 80 ? 'excellent' : 'average',
            recommendation: 'recommended',
            gates: [],
            profile_revision_id: 1,
            intent_revision_id: 1,
            created_at: '2026-10-08T10:05:00Z',
          },
    signals: [
      {
        dimension_key: 'work_arrangement_location',
        status: 'match',
        quality: 'strong',
        excluded: false,
      },
    ],
    sources: [
      {
        job_posting_id: 200 + job.id,
        source_type: 'greenhouse',
        source_name: 'Northwind Careers',
        url: `https://jobs.example.test/${job.id}`,
        first_seen_at: '2026-10-08T10:00:00Z',
        closed: false,
        job_opportunity_link_id: 300 + job.id,
        link_state: 'auto',
        similarity: 1,
      },
    ],
    possible_duplicate: false,
    engagement_types: [],
    pay: null,
    applied_at: job.state === 'applied' ? '2026-10-08T12:00:00Z' : null,
    note: null,
  })

  const counts = () => ({
    unread: jobs.filter((j) => j.state === 'unread').length,
    read: jobs.filter((j) => j.state === 'read').length,
    updated_unread: 0,
    set_aside: 0,
    ignored: jobs.filter((j) => j.state === 'ignored').length,
    archived: 0,
    applied: jobs.filter((j) => j.state === 'applied').length,
    shortlisted: jobs.filter((j) => j.shortlisted).length,
    total: jobs.length,
  })

  return async (route: Route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname.replace('/api/v1', '')
    const method = request.method()

    if (path === '/profiles') {
      return json(route, {
        items: [
          {
            career_profile_id: 1,
            title: 'AI Solutions',
            visibility: 'private',
            version: 2,
            current_revision: null,
          },
        ],
      })
    }
    if (path === '/profiles/1/intents') {
      return json(route, {
        items: [
          {
            search_intent_id: 5,
            career_profile_id: 1,
            title: 'Remote first',
            enabled: true,
            version: 1,
            current_revision: null,
          },
        ],
      })
    }
    if (path === '/inbox' && method === 'GET') {
      const state = url.searchParams.get('state') ?? 'unread'
      const shortlisted = url.searchParams.get('shortlisted') === 'true'
      const items = jobs
        .filter(
          (j) => (state === 'all' ? true : j.state === state) && (!shortlisted || j.shortlisted),
        )
        .sort((a, b) => (b.score ?? -1) - (a.score ?? -1))
      return json(route, {
        items: items.map(summary),
        next_cursor: null,
        counts: counts(),
        set_aside_below_fit: 0,
        search_intent_id: 5,
      })
    }
    const detail = path.match(/^\/inbox\/(\d+)$/)
    if (detail && method === 'GET') {
      const job = jobs.find((j) => j.id === Number(detail[1]))!
      return json(route, {
        ...summary(job),
        description_text: 'Design and evaluate LLM-powered features.',
        apply_url: `https://careers.example.test/apply/${job.id}`,
        read_at: null,
        ignore_reason: null,
        application_url: null,
        dimensions: [],
        events: [],
        last_change: null,
        brief: { summary: null, summary_model: null, technologies: [], facts: [] },
      })
    }
    const act = path.match(/^\/inbox\/(\d+)\/actions$/)
    if (act && method === 'POST') {
      const job = jobs.find((j) => j.id === Number(act[1]))!
      const body = request.postDataJSON() as { action: string; expected_version: number }
      if (body.expected_version !== job.version) {
        return json(
          route,
          {
            error: {
              code: 'conflict',
              message: 'The inbox item changed since it was loaded.',
              details: {},
              request_id: 'x',
            },
          },
          409,
        )
      }
      if (body.action === 'shortlist') job.shortlisted = true
      else if (body.action === 'unshortlist') job.shortlisted = false
      else {
        const rule = NEXT[body.action]
        if (!rule || !rule.from.includes(job.state)) {
          return json(
            route,
            {
              error: {
                code: 'validation_error',
                message: `'${body.action}' is not allowed while the item is ${job.state}.`,
                details: {},
                request_id: 'x',
              },
            },
            422,
          )
        }
        job.state = rule.to
      }
      job.version += 1
      return json(route, {
        item: summary(job),
        event: {
          inbox_event_id: 1,
          action: body.action,
          actor: 'user',
          from_state: null,
          to_state: job.state,
          created_at: '2026-10-08T12:00:00Z',
        },
      })
    }
    return route.continue()
  }
}

test.beforeEach(async ({ page }) => {
  await page.route('**/api/v1/**', createStub())
})

test('shortlist, ignore and undo, restore, and applied with undo', async ({ page }) => {
  await page.goto('/inbox')
  await expect(page.getByRole('option', { name: /Senior AI Solutions Engineer/ })).toBeVisible()
  const detail = page.getByRole('article', { name: /Senior AI Solutions Engineer/ })
  await expect(detail.getByRole('meter', { name: 'Fit score' })).toHaveAttribute(
    'aria-valuenow',
    '82',
  )

  // shortlist from the detail panel, then see it in the Shortlist section
  await detail.getByRole('button', { name: /Shortlist/ }).click()
  await expect(page.getByRole('status').filter({ hasText: 'Added to shortlist' })).toBeVisible()
  await page.getByRole('tab', { name: /Shortlist/ }).click()
  await expect(page.getByRole('option', { name: /Senior AI Solutions Engineer/ })).toBeVisible()
  await page.getByRole('tab', { name: /To review/ }).click()

  // ignore, then undo from the toast: the job is back (unread) in the review list
  await page.getByRole('button', { name: /^Ignore/ }).click()
  await expect(page.getByRole('status').filter({ hasText: 'Ignored' })).toBeVisible()
  await expect(page.getByRole('option', { name: /Senior AI Solutions Engineer/ })).toHaveCount(0)
  await page
    .getByRole('status')
    .filter({ hasText: 'Ignored' })
    .getByRole('button', { name: /Undo/ })
    .click()
  await expect(page.getByRole('option', { name: /Senior AI Solutions Engineer/ })).toBeVisible()

  // ignore again, restore it from the Ignored section
  await page.getByRole('button', { name: /^Ignore/ }).click()
  await page.getByRole('tab', { name: /Ignored/ }).click()
  const ignored = page.getByRole('article', { name: /Senior AI Solutions Engineer/ })
  await expect(ignored.getByText(/this job is ignored/i)).toBeVisible()
  await ignored.getByRole('button', { name: /Restore/ }).click()
  await page.getByRole('tab', { name: /Reviewed/ }).click()
  await expect(page.getByRole('option', { name: /Senior AI Solutions Engineer/ })).toBeVisible()

  // mark applied (from reviewed), then undo it
  await page.getByRole('button', { name: /Mark applied/ }).click()
  await expect(page.getByRole('status').filter({ hasText: 'Marked as applied' })).toBeVisible()
  await page.getByRole('tab', { name: /Applied/ }).click()
  await expect(page.getByRole('option', { name: /Senior AI Solutions Engineer/ })).toBeVisible()
  await page.getByRole('button', { name: /Undo applied/ }).click()
  await page.getByRole('tab', { name: /Reviewed/ }).click()
  await expect(page.getByRole('option', { name: /Senior AI Solutions Engineer/ })).toBeVisible()
})

test('keyboard: j moves down and ? shows the shortcuts', async ({ page }) => {
  await page.goto('/inbox')
  await expect(page.getByRole('article', { name: /Senior AI Solutions Engineer/ })).toBeVisible()
  await page.keyboard.press('j')
  await expect(page.getByRole('article', { name: /Platform Engineer/ })).toBeVisible()
  await page.keyboard.press('?')
  await expect(page.getByRole('dialog', { name: 'Keyboard shortcuts' })).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).toHaveCount(0)
})

test('density is remembered after a reload', async ({ page }) => {
  await page.goto('/inbox')
  await page.getByRole('button', { name: 'Compact' }).click()
  await page.reload()
  await expect(page.getByTestId('inbox-root')).toHaveAttribute('data-density', 'compact')
})

test('opening the original leaves the job in To review until a button moves it', async ({
  page,
}) => {
  await page.goto('/inbox')
  const first = page.getByRole('option', { name: /Senior AI Solutions Engineer/ })
  const detail = page.getByRole('article', { name: /Senior AI Solutions Engineer/ })
  const link = detail.getByRole('link', { name: /open original/i })
  await link.evaluate((a) => a.addEventListener('click', (e) => e.preventDefault())) // stay on the page
  await link.click()
  await page.getByRole('option', { name: /Platform Engineer/ }).click()
  await expect(page.getByRole('article', { name: /Platform Engineer/ })).toBeVisible()
  await expect(first).toBeVisible()
})
