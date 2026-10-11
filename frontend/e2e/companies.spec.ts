import { expect, test, type Route } from '@playwright/test'

/** Companies and Trends against a stub of the API (no database, no public dataset is contacted). */

const json = (route: Route, body: unknown, status = 200) => route.fulfill({ status, json: body })

const COMPANY = {
  company_id: 1,
  name: 'Northwind Labs',
  homepage_url: null,
  careers_url: null,
  employer_type: null,
  open_offers: 4,
  recommended_offers: 2,
  best_fit_score: 82,
  pending_candidates: 0,
  is_followed: false,
}

const DOSSIER = {
  company_id: 1,
  name: 'Northwind Labs',
  homepage_url: 'https://www.northwind.example/',
  careers_url: null,
  employer_type: null,
  enriched_at: '2026-10-08T09:00:00Z',
  stale: false,
  is_followed: false,
  offers_truncated: false,
  facts: [
    {
      fact_key: 'industry',
      value: 'software industry',
      origin: 'public_dataset',
      label: 'Source',
      source_name: 'wikidata',
      source_url: 'https://www.wikidata.org/wiki/Q1',
      retrieved_at: '2026-10-08T09:00:00Z',
      licence: 'CC0-1.0',
      confidence: null,
    },
  ],
  candidates: [],
  offers: [],
  hiring: Array.from({ length: 12 }, (_, i) => ({
    week_start: `2026-07-${String(i + 1).padStart(2, '0')}`,
    new_offers: i % 4,
    open_offers: i,
  })),
  boards: [],
  warnings: [],
}

const TREND = {
  kind: 'skill',
  search_intent_id: 1,
  relevance_min_score: 45,
  available_weeks: 4,
  first_week: '2026-09-14',
  periods: [
    { key: '4w', weeks: 4, available: true },
    { key: '12w', weeks: 12, available: false },
    { key: '6m', weeks: 26, available: false },
  ],
  weeks: [],
  rows: [
    {
      term_key: '1',
      label: 'Python',
      open_now: 5,
      share_now: 0.5,
      share_change: 0.1,
      count_change: 2,
      series: [0.4, 0.45, 0.5].map((share, i) => ({
        week_start: `2026-09-${14 + i * 7}`,
        open_count: 3 + i,
        share,
      })),
    },
  ],
  intent_revision_changes: [],
  source_set_changes: [],
}

test('the company list opens a dossier with sourced facts', async ({ page }) => {
  await page.route('**/api/v1/**', (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/v1/companies')
      return json(route, {
        items: [COMPANY],
        total: 1,
        sort: 'fit',
        search_intent_id: 1,
        relevance_min_score: 45,
        recency_days: 30,
      })
    if (path === '/api/v1/companies/1') return json(route, DOSSIER)
    return json(route, { error: { code: 'not_found', message: 'unexpected', details: {} } }, 404)
  })
  await page.goto('/companies')
  await page.getByRole('option', { name: /Northwind Labs/ }).click()
  const panel = page.getByRole('region', { name: 'Northwind Labs' })
  await expect(panel.getByText('software industry')).toBeVisible()
  await expect(panel.getByText(/wikidata · CC0-1\.0/)).toBeVisible()
  await expect(panel.getByRole('group', { name: /new offers per week/i })).toBeVisible()
  await expect(page).toHaveURL(/company=1/)
})

test('trends show shares and keep longer periods locked', async ({ page }) => {
  await page.route('**/api/v1/trends**', (route) => json(route, TREND))
  await page.goto('/trends')
  await expect(page.getByText(/History available:/)).toContainText('4 weeks')
  await expect(page.getByRole('button', { name: '12 weeks' })).toBeDisabled()
  const table = page.getByRole('table', { name: 'Technologies' })
  await expect(table.getByRole('row', { name: /Python/ })).toContainText('50%')
})
