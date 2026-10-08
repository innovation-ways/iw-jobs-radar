import type { components } from '@/api/schema'

export type FitBand = components['schemas']['EvaluationBrief']['fit_band']
export type BandTone = 'good' | 'caution' | 'neutral' | 'bad'

export interface BandInfo {
  /** Full label shown in the detail panel. */
  label: string
  /** Short label for the score tile. */
  short: string
  tone: BandTone
}

const BANDS: Record<FitBand, BandInfo> = {
  excellent: { label: 'Excellent fit', short: 'Excellent', tone: 'good' },
  strong: { label: 'Strong fit', short: 'Strong', tone: 'good' },
  average: { label: 'Average fit', short: 'Average', tone: 'caution' },
  low: { label: 'Low fit', short: 'Low', tone: 'neutral' },
  not_recommended: { label: 'Not recommended', short: 'Not rec.', tone: 'bad' },
}

/** How a job without a score is shown: it is listed, never hidden. */
export const NOT_EVALUATED: BandInfo = { label: 'Not evaluated', short: 'Pending', tone: 'neutral' }

/** Label, short label and tone for a fit band (document 13, section 7.7). */
export function bandOf(band: FitBand): BandInfo {
  return BANDS[band]
}

/** Tailwind classes for a tone: soft background and text colour (colour is never the only cue). */
export const TONE_CLASSES: Record<BandTone, { soft: string; fill: string }> = {
  good: { soft: 'bg-good-bg text-good', fill: 'bg-good' },
  caution: { soft: 'bg-caution-bg text-caution', fill: 'bg-caution' },
  neutral: { soft: 'bg-band-bg text-band', fill: 'bg-band' },
  bad: { soft: 'bg-bad-bg text-bad', fill: 'bg-bad' },
}
