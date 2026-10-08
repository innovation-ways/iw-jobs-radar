import { expect, test } from '@playwright/test'

test('the app shell loads, shows backend readiness and navigates', async ({ page }) => {
  await page.goto('/')
  await expect(page).toHaveURL(/\/inbox$/)
  await expect(page.getByRole('heading', { level: 1, name: 'Inbox' })).toBeVisible()

  const nav = page.getByRole('navigation', { name: 'Main navigation' })
  await expect(nav.getByRole('link')).toHaveCount(7)

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
