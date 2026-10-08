import type { components } from '@/api/schema'

export type Signal = components['schemas']['SignalRead']

/** The facts that usually decide "look or skip", in the order they appear on a card. */
const CARD_DIMENSIONS: [key: string, label: string][] = [
  ['work_arrangement_location', 'Work'],
  ['engagement_terms', 'Engagement'],
  ['compensation', 'Pay'],
  ['skills_technology', 'Skills'],
]

/** A symbol and words for a status; a partial match is shown as "~" so it is not mistaken for a full one. */
export function signalIcon(signal: Pick<Signal, 'status' | 'quality'>): {
  symbol: string
  word: string
} {
  if (signal.status === 'match') {
    return signal.quality === 'strong'
      ? { symbol: '✓', word: 'match' }
      : { symbol: '~', word: 'partial match' }
  }
  return signal.status === 'mismatch'
    ? { symbol: '✕', word: 'mismatch' }
    : { symbol: '?', word: 'unknown' }
}

export interface CardSignal {
  key: string
  label: string
  symbol: string
  word: string
  status: Signal['status']
}

/** The signals shown on a job card (excluded dimensions are left out). */
export function cardSignals(signals: Signal[]): CardSignal[] {
  const result: CardSignal[] = []
  for (const [key, label] of CARD_DIMENSIONS) {
    const signal = signals.find((s) => s.dimension_key === key)
    if (!signal || signal.excluded) continue
    result.push({ key, label, status: signal.status, ...signalIcon(signal) })
  }
  return result
}
