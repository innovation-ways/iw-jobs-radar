import { describe, expect, it } from 'vitest'
import { describeApiError } from './errors'

describe('describeApiError', () => {
  it('uses the message and error class of the API error envelope', () => {
    const body = {
      error: {
        code: 'validation_error',
        message: 'The board was not found. Check the board token.',
        details: { error_class: 'not_found' },
        request_id: 'r1',
      },
    }
    expect(describeApiError(body)).toEqual({
      message: 'The board was not found. Check the board token.',
      errorClass: 'not_found',
    })
  })

  it('has no error class when the envelope does not carry one', () => {
    const body = { error: { code: 'conflict', message: 'Already there.', details: {} } }
    expect(describeApiError(body)).toEqual({ message: 'Already there.', errorClass: null })
  })

  it('summarises request validation errors without echoing values', () => {
    const body = {
      error: {
        code: 'validation_error',
        message: 'Request validation failed.',
        details: { errors: [{ loc: ['body', 'x'], msg: 'Field required', type: 'missing' }] },
      },
    }
    expect(describeApiError(body).message).toBe('Request validation failed.')
  })

  it('falls back to a generic message for anything else', () => {
    expect(describeApiError(undefined).message).toMatch(/unexpected/i)
    expect(describeApiError('boom').message).toMatch(/unexpected/i)
    expect(describeApiError(new Error('network')).message).toMatch(/could not reach/i)
  })
})
