import { expect, test, type Route } from '@playwright/test'

/**
 * CV import against a stub of the API (no database, no real provider, no real CV): choose a file,
 * confirm sending it to a remote provider, review the proposals and apply them.
 */

const json = (route: Route, body: unknown, status = 200) => route.fulfill({ status, json: body })

const PROFILE = {
  career_profile_id: 1,
  title: 'Imported',
  visibility: 'private',
  version: 1,
  current_revision: null,
}

const AI = {
  mode: 'remote',
  import_connection_id: 1,
  jobs_connection_id: null,
  key_configured: true,
  connections: [
    {
      provider_connection_id: 1,
      provider_type: 'openai',
      display_name: 'Test provider',
      endpoint_url: 'https://api.example.test/v1',
      model_id: 'model-x',
      credential_status: 'saved',
      credential_updated_at: null,
      processing_location: 'remote',
      is_active: true,
      use_for_jobs: false,
      version: 1,
    },
  ],
  privacy: { redact_contact_details: true, version: 1 },
}

const ITEMS = [
  {
    proposal_item_id: 11,
    path: 'headline',
    value: 'Senior Software Engineer',
    source_excerpt: 'Senior Software Engineer',
    confidence: 0.9,
    review_status: 'pending',
    edited_value: null,
    reviewed_at: null,
  },
  {
    proposal_item_id: 12,
    path: 'skills',
    value: { name: 'Python', kind: 'technology', level: 'expert', years: 8 },
    source_excerpt: 'Python (expert, 8 years)',
    confidence: 0.8,
    review_status: 'pending',
    edited_value: null,
    reviewed_at: null,
  },
]

test('import a CV: consent, proposals, review and a new revision', async ({ page }) => {
  const seen: { consent?: unknown; decisions?: unknown } = {}
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url())
    const method = route.request().method()
    const path = url.pathname
    if (path === '/api/v1/profiles' && method === 'GET') return json(route, { items: [PROFILE] })
    if (path === '/api/v1/taxonomy') return json(route, { groups: [] })
    if (path === '/api/v1/profiles/1/intents') return json(route, { items: [] })
    if (path === '/api/v1/settings/ai') return json(route, AI)
    if (path === '/api/v1/documents' && method === 'POST')
      return json(
        route,
        {
          document_id: 40,
          sha256: 'a'.repeat(64),
          mime_type: 'text/plain',
          byte_size: 2048,
          extraction_status: 'extracted',
          extraction_version: 'extract-v1',
          pages: null,
          characters: 900,
          text_available: true,
          created_at: '2026-10-08T10:00:00Z',
        },
        201,
      )
    if (path === '/api/v1/documents/40/proposals') {
      seen.consent = route.request().postDataJSON().consent
      return json(
        route,
        {
          profile_proposal_id: 5,
          career_profile_id: 1,
          document_id: 40,
          provider_type: 'openai',
          provider_model: 'model-x',
          prompt_version: 'profile-import-v1',
          redaction_policy: 'contact-v1',
          consent: {},
          status: 'pending',
          completed_at: null,
          created_at: '2026-10-08T10:01:00Z',
          items: ITEMS,
        },
        201,
      )
    }
    if (path === '/api/v1/profiles/1/reviews') {
      seen.decisions = route.request().postDataJSON().decisions
      return json(route, {
        created: true,
        profile: { ...PROFILE, current_revision: { revision_number: 1 } },
        proposal: { status: 'completed', items: ITEMS },
      })
    }
    return json(route, { error: { code: 'not_found', message: 'unexpected', details: {} } }, 404)
  })

  await page.goto('/profile')
  await page.getByRole('tab', { name: 'Import CV' }).click()
  await expect(page.getByText('Original file is not stored')).toBeVisible()
  await page.getByLabel('Choose a CV file').setInputFiles({
    name: 'synthetic-cv.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('Synthetic CV text for the test'),
  })
  await expect(page.getByText(/synthetic-cv\.txt/)).toBeVisible()

  const generate = page.getByRole('button', { name: 'Generate proposals' })
  await expect(generate).toBeDisabled() // no consent yet
  await page.getByLabel(/I agree to send this CV/).check()
  await generate.click()
  expect(seen.consent).toEqual({ provider_connection_id: 1, model_id: 'model-x' })

  await page
    .getByRole('radiogroup', { name: /Headline/ })
    .getByText('Accept')
    .click()
  await page.getByRole('radiogroup', { name: /Skill/ }).getByText('Reject').click()
  await expect(page.getByText('2 of 2 decided')).toBeVisible()
  await page.getByRole('button', { name: /apply review/i }).click()
  await expect(page.getByText(/revision 1 was created/i)).toBeVisible()
  expect(seen.decisions).toEqual([
    { proposal_item_id: 11, decision: 'accept' },
    { proposal_item_id: 12, decision: 'reject' },
  ])
})

test('AI & privacy starts as No AI and never shows a stored key', async ({ page }) => {
  await page.route('**/api/v1/**', (route) =>
    json(route, {
      ...AI,
      mode: 'no_ai',
      import_connection_id: null,
    }),
  )
  await page.goto('/settings')
  await expect(page.getByText(/jobs are still collected/i)).toBeVisible()
  const key = page.getByLabel('API key')
  await expect(key).toHaveAttribute('type', 'password')
  await expect(page.getByText('Credential: saved')).toBeVisible()
  await expect(page.locator('body')).not.toContainText('sk-')
})
