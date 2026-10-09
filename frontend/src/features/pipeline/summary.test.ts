import { describe, expect, it } from 'vitest'
import { formatMinutes, headline, pace, type PipelineStatus } from './summary'

function status(overrides: Partial<PipelineStatus> = {}): PipelineStatus {
  return {
    state: 'working',
    ai_model: 'qwen3:8b',
    worker: { status: 'up', last_beat_at: '2026-10-09T12:00:00Z' },
    analysis: {
      total: 653,
      done: 211,
      failed: 2,
      waiting: 440,
      search_intent_id: null,
      minutes_left: 147,
    },
    scoring: {
      total: 211,
      done: 40,
      failed: 0,
      waiting: 171,
      search_intent_id: 4,
      minutes_left: 30,
    },
    recent: {
      window_minutes: 15,
      analysed: 45,
      scored: 12,
      analysed_per_minute: 3,
      scored_per_minute: 0.8,
    },
    failures: {
      count: 2,
      last_error_class: 'schema_invalid',
      last_failed_at: '2026-10-09T11:50:00Z',
    },
    generated_at: '2026-10-09T12:00:10Z',
    ...overrides,
  }
}

describe('formatMinutes', () => {
  it('shows minutes, then hours and minutes', () => {
    expect(formatMinutes(1)).toBe('~1 min')
    expect(formatMinutes(45)).toBe('~45 min')
    expect(formatMinutes(60)).toBe('~1 h')
    expect(formatMinutes(147)).toBe('~2 h 27 min')
  })
})

describe('headline', () => {
  it('describes the analysis while jobs wait to be analysed', () => {
    expect(headline(status())).toBe('Analysing 211 of 653')
  })

  it('moves to scoring when nothing waits for analysis', () => {
    const s = status({ analysis: { ...status().analysis, waiting: 0, done: 651 } })
    expect(headline(s)).toBe('Scoring 40 of 211')
  })

  it('says so when everything is done', () => {
    const s = status({
      state: 'idle',
      analysis: { ...status().analysis, waiting: 0 },
      scoring: { ...status().scoring, waiting: 0 },
    })
    expect(headline(s)).toBe('Up to date')
  })

  it('names the problem states in words', () => {
    expect(headline(status({ state: 'no_ai' }))).toBe('Job analysis is off')
    expect(headline(status({ state: 'worker_stopped' }))).toBe('Worker not responding')
    expect(headline(status({ state: 'no_progress' }))).toBe('No progress in the last 15 min')
  })
})

describe('pace', () => {
  it('gives the pace and the time left', () => {
    expect(pace(status().analysis, status().recent.analysed_per_minute)).toBe(
      '3/min · ~2 h 27 min left',
    )
  })

  it('omits what is unknown', () => {
    const queue = { ...status().analysis, minutes_left: null }
    expect(pace(queue, 0)).toBe('no recent progress')
    expect(pace({ ...queue, waiting: 0 }, 0)).toBe('')
  })
})
