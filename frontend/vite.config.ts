/// <reference types="vitest/config" />
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'
import { defineConfig, loadEnv } from 'vite'

// Ports come from the repository .env (ADR-019); nothing is hardcoded here beyond safe defaults.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, path.resolve(import.meta.dirname, '..'), 'JOBS_RADAR_')
  const apiPort = process.env.JOBS_RADAR_API_PORT ?? env.JOBS_RADAR_API_PORT ?? '8100'
  const target = `http://127.0.0.1:${apiPort}`
  // Host names the dev server accepts. Vite blocks unknown Host headers (DNS-rebinding protection),
  // so a machine name such as iw-dev-01 must be listed explicitly instead of disabling the check.
  const allowedHosts = (
    process.env.JOBS_RADAR_FRONTEND_ALLOWED_HOSTS ??
    env.JOBS_RADAR_FRONTEND_ALLOWED_HOSTS ??
    'localhost,127.0.0.1'
  )
    .split(',')
    .map((host) => host.trim())
    .filter(Boolean)
  return {
    plugins: [react(), tailwindcss()],
    resolve: { alias: { '@': path.resolve(import.meta.dirname, 'src') } },
    server: {
      allowedHosts,
      // Same-origin calls in development: the browser talks to Vite, Vite talks to the API.
      proxy: { '/api': target, '/healthz': target, '/readyz': target },
    },
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: ['./src/test/setup.ts'],
      css: false,
      exclude: ['e2e/**', 'node_modules/**'],
      coverage: {
        provider: 'v8',
        include: ['src/**'],
        exclude: ['src/api/schema.d.ts', 'src/test/**'],
      },
    },
  }
})
