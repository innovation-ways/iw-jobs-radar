import { expect, test, type Route } from '@playwright/test'

/**
 * Profile & intent flow against a stateful in-memory stub of the API (no database is touched and
 * no real request is made): create a profile, create an intent, change a weight, see History.
 */

type Json = Record<string, unknown>

const TAXONOMY = {
  groups: [
    {
      kind: 'role_family',
      terms: [{ term_key: 'ai_solutions_engineering', label: 'AI solutions engineering' }],
    },
    {
      kind: 'work_arrangement',
      terms: [
        { term_key: 'remote', label: 'Remote' },
        { term_key: 'onsite', label: 'On-site' },
      ],
    },
    {
      kind: 'engagement_type',
      terms: [{ term_key: 'employee_permanent', label: 'Permanent employee' }],
    },
    { kind: 'seniority_level', terms: [{ term_key: 'senior', label: 'Senior' }] },
    { kind: 'sector', terms: [{ term_key: 'telecom', label: 'Telecom' }] },
    { kind: 'employer_type', terms: [{ term_key: 'direct_employer', label: 'Direct employer' }] },
    { kind: 'benefit', terms: [] },
  ],
}

const LISBON = {
  label: 'Lisbon, Portugal',
  city: 'Lisbon',
  country: 'PT',
  latitude: 38.72509,
  longitude: -9.1498,
  timezone: 'Europe/Lisbon',
  population: 517802,
}

function createStub() {
  let profile: Json | null = null
  const profileRevisions: Json[] = []
  let intent: Json | null = null
  const intentRevisions: Json[] = []
  const now = () => new Date().toISOString()

  const profileRead = () => ({
    career_profile_id: 1,
    title: profile!.title,
    visibility: 'private',
    version: profileRevisions.length + 1,
    current_revision: profileRevisions[0] ?? null,
  })
  const intentRead = () => ({
    search_intent_id: 7,
    career_profile_id: 1,
    title: (intentRevisions[0]!.definition as Json).title,
    enabled: true,
    version: intentRevisions.length,
    current_revision: intentRevisions[0],
  })
  const json = (route: Route, body: unknown, status = 200) => route.fulfill({ status, json: body })

  return async (route: Route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname.replace('/api/v1', '')
    const method = request.method()
    const body = request.postDataJSON() as Json | null

    if (path === '/profiles' && method === 'GET')
      return json(route, { items: profile ? [profileRead()] : [] })
    if (path === '/profiles' && method === 'POST') {
      profile = { title: body!.title }
      return json(route, profileRead(), 201)
    }
    if (path === '/profiles/1' && method === 'PUT') {
      const revision = {
        profile_revision_id: 100 + profileRevisions.length,
        revision_number: profileRevisions.length + 1,
        created_at: now(),
        change_summary: body!.change_summary ?? null,
        privacy: body!.privacy,
        facts: {
          schema_version: 1,
          headline: body!.headline,
          base_location: body!.base_location,
          years_experience: body!.years_experience,
          languages: body!.languages,
          skills: [],
          experience: [],
          education: [],
          certifications: [],
        },
      }
      profileRevisions.unshift(revision)
      return json(route, { created: true, profile: profileRead() })
    }
    if (path === '/taxonomy') return json(route, TAXONOMY)
    if (path === '/profiles/1/intents' && method === 'GET')
      return json(route, { items: intent ? [intentRead()] : [] })
    if (path === '/profiles/1/intents' && method === 'POST') {
      const definition = { ...body! }
      delete definition.enabled
      intentRevisions.unshift({
        intent_revision_id: 200,
        revision_number: 1,
        created_at: now(),
        change_summary: null,
        definition,
      })
      intent = {}
      return json(route, intentRead(), 201)
    }
    if (path === '/intents/7' && method === 'PUT') {
      const definition = { ...body! }
      delete definition.expected_current_revision
      const change_summary = definition.change_summary
      delete definition.change_summary
      intentRevisions.unshift({
        intent_revision_id: 200 + intentRevisions.length,
        revision_number: intentRevisions.length + 1,
        created_at: now(),
        change_summary: change_summary ?? null,
        definition,
      })
      return json(route, { created: true, intent: intentRead() })
    }
    if (path === '/profiles/1/revisions') {
      return json(route, {
        items: profileRevisions.map(
          ({ profile_revision_id, revision_number, created_at, change_summary }) => ({
            profile_revision_id,
            revision_number,
            created_at,
            change_summary,
          }),
        ),
      })
    }
    if (path === '/intents/7/revisions') return json(route, { items: intentRevisions })
    if (path === '/locations/search') return json(route, { items: [LISBON] })
    return route.continue()
  }
}

test('create a profile and an intent, change a weight and see both in History', async ({
  page,
}) => {
  await page.route('**/api/v1/**', createStub())
  await page.goto('/profile')

  await expect(page.getByText('Create your first profile')).toBeVisible()
  await page.getByLabel('Profile name').fill('AI Solutions')
  await page.getByRole('button', { name: 'Create profile' }).click()

  await page.getByLabel('Headline').fill('AI solutions engineer')
  await page.getByRole('combobox', { name: 'Base place' }).fill('lis')
  await page.getByRole('option', { name: /Lisbon, Portugal/ }).click()
  await page.getByRole('button', { name: 'Save revision' }).click()
  await expect(page.getByLabel('Career profile')).toContainText('revision 1')

  await page.getByRole('tab', { name: 'Search intent' }).click()
  await page.getByRole('button', { name: 'Create search intent' }).click()
  await expect(page.getByLabel('Intent name')).toHaveValue('My search')

  await page.getByRole('tab', { name: 'Scoring weights' }).click()
  const compensation = page.getByRole('slider', { name: 'Compensation weight' })
  await compensation.focus()
  await compensation.press('ArrowRight')
  await compensation.press('ArrowRight')
  await expect(page.getByText('12', { exact: true }).first()).toBeVisible()
  await page.getByLabel(/change note/i).fill('More weight on pay')
  await page.getByRole('button', { name: 'Save revision' }).click()
  await expect(page.getByLabel('Search intent')).toContainText('revision 2')

  await page.getByRole('tab', { name: 'History' }).click()
  const intentTable = page.getByRole('table', { name: 'Intent revisions' })
  await expect(intentTable.getByRole('row')).toHaveCount(3) // header + revisions 2 and 1
  await expect(intentTable).toContainText('More weight on pay')
  await expect(page.getByRole('table', { name: 'Profile revisions' })).toBeVisible()
})

test('nothing sensitive is kept in the browser while editing', async ({ page }) => {
  await page.route('**/api/v1/**', createStub())
  await page.goto('/profile')
  await page.getByLabel('Profile name').fill('Private profile')
  await page.getByRole('button', { name: 'Create profile' }).click()
  await page.getByLabel('Headline').fill('Secret headline')
  const stored = await page.evaluate(
    () => JSON.stringify({ ...localStorage }) + JSON.stringify({ ...sessionStorage }),
  )
  expect(stored).not.toContain('Secret headline')
})
