import { expect, test } from '@playwright/test'

test('the app shell loads, shows backend readiness and navigates', async ({ page }) => {
  await page.goto('/')
  await expect(page).toHaveURL(/\/inbox$/)
  await expect(page.getByRole('heading', { level: 1, name: 'Inbox' })).toBeVisible()

  const nav = page.getByRole('navigation', { name: 'Main navigation' })
  await expect(nav.getByRole('link')).toHaveCount(9)

  // The worker heartbeat makes the backend report "ready" (ADR-031).
  await expect(page.getByRole('status')).toContainText('API ready', { timeout: 30_000 })

  await nav.getByRole('link', { name: 'Trends' }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Trends' })).toBeVisible()
})

test('the theme choice is applied and survives a reload', async ({ page }) => {
  await page.goto('/inbox')
  await page.getByRole('button', { name: 'Dark' }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  await page.reload()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
})

test('an unknown address shows a not-found page', async ({ page }) => {
  await page.goto('/nowhere')
  await expect(page.getByRole('heading', { level: 1, name: 'Page not found' })).toBeVisible()
})

test('the Sources screen shows boards and their status (API stubbed, no real network)', async ({
  page,
}) => {
  const result = {
    collection_run_id: 1,
    source_configuration_id: 1,
    outcome: 'success',
    started_at: '2026-10-08T07:30:00Z',
    finished_at: '2026-10-08T07:30:05Z',
    collected_count: 3,
    new_count: 3,
    updated_count: 0,
    deduplicated_count: 0,
    closed_count: 0,
    http_status: 200,
    error_class: null,
    error_message: null,
    duration_ms: 5000,
  }
  await page.route('**/api/v1/sources', (route) =>
    route.fulfill({
      json: {
        items: [
          {
            source_configuration_id: 1,
            source_type: 'greenhouse',
            external_identifier: 'example-board',
            display_name: 'Example Co',
            company_id: 1,
            company_name: 'Example Co',
            url: 'https://boards.example.test/v1/boards/example-board/jobs',
            enabled: true,
            rate_limit_per_minute: 6,
            version: 1,
            open_postings: 3,
            last_result: result,
          },
        ],
      },
    }),
  )
  await page.route('**/api/v1/collection-runs?*', (route) =>
    route.fulfill({ json: { items: [], next_before_collection_run_id: null } }),
  )

  await page.goto('/sources')
  await expect(page.getByRole('heading', { level: 1, name: 'Sources' })).toBeVisible()
  const row = page.getByRole('row', { name: /Example Co/ })
  await expect(row).toContainText('Succeeded')
  await expect(page.getByRole('heading', { name: 'Daily schedule' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Validate & add' })).toBeDisabled()
})
