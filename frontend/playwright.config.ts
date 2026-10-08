import { defineConfig } from '@playwright/test'
import { existsSync, readFileSync } from 'node:fs'
import path from 'node:path'

// The browser must already be installed; this project never downloads browsers (CLAUDE.md).
// Set JOBS_RADAR_CHROMIUM_PATH, or reuse the executable configured for playwright-cli.
function chromiumPath(): string | undefined {
  if (process.env.JOBS_RADAR_CHROMIUM_PATH) return process.env.JOBS_RADAR_CHROMIUM_PATH
  const cliConfig = path.resolve(import.meta.dirname, '../.playwright/cli.config.json')
  if (existsSync(cliConfig)) {
    return JSON.parse(readFileSync(cliConfig, 'utf8'))?.browser?.launchOptions?.executablePath
  }
  return undefined
}

const port = process.env.JOBS_RADAR_FRONTEND_PORT ?? '5180'

export default defineConfig({
  testDir: './e2e',
  // Runs against the stack started by ./jobs-radar.sh; synthetic data only.
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    launchOptions: { executablePath: chromiumPath(), args: ['--no-sandbox'] },
  },
  reporter: [['list']],
})
