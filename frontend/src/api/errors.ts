/** An API failure reduced to what the owner should read; never carries submitted values. */
export class ApiError extends Error {
  readonly errorClass: string | null

  constructor(message: string, errorClass: string | null = null) {
    super(message)
    this.name = 'ApiError'
    this.errorClass = errorClass
  }
}

const UNEXPECTED = 'The server answered with an unexpected error.'
const UNREACHABLE = 'Could not reach the server. Check that the API is running and try again.'

/**
 * Turn whatever a failed call produced into a message and an optional machine-readable class.
 * Understands the API error envelope `{ error: { message, details: { error_class } } }`.
 */
export function describeApiError(error: unknown): { message: string; errorClass: string | null } {
  if (error instanceof ApiError) return { message: error.message, errorClass: error.errorClass }
  if (error instanceof Error) return { message: UNREACHABLE, errorClass: null }
  if (typeof error === 'object' && error !== null && 'error' in error) {
    const inner = (error as { error: unknown }).error
    if (typeof inner === 'object' && inner !== null && 'message' in inner) {
      const { message, details } = inner as { message: unknown; details?: unknown }
      if (typeof message === 'string') {
        const errorClass =
          typeof details === 'object' && details !== null && 'error_class' in details
            ? (details as { error_class: unknown }).error_class
            : null
        return { message, errorClass: typeof errorClass === 'string' ? errorClass : null }
      }
    }
  }
  return { message: UNEXPECTED, errorClass: null }
}

/** Return the data of an API call or throw an {@link ApiError} describing why there is none. */
export async function unwrap<T>(call: Promise<{ data?: T; error?: unknown }>): Promise<T> {
  let result: { data?: T; error?: unknown }
  try {
    result = await call
  } catch (error) {
    const { message, errorClass } = describeApiError(error)
    throw new ApiError(message, errorClass)
  }
  if (result.data === undefined) {
    const { message, errorClass } = describeApiError(result.error)
    throw new ApiError(message, errorClass)
  }
  return result.data
}
