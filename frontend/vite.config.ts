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
  return {
    plugins: [react(), tailwindcss()],
    resolve: { alias: { '@': path.resolve(import.meta.dirname, 'src') } },
    server: {
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
