import createClient from 'openapi-fetch'
import type { paths } from './schema'

/**
 * Typed API client generated from the backend OpenAPI document (`pnpm api:generate`).
 * Same-origin: in development Vite proxies /api, /healthz and /readyz to the backend.
 */
export const api = createClient<paths>({ baseUrl: '' })
