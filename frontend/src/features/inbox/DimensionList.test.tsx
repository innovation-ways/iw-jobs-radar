import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { DimensionList } from './DimensionList'
import type { InboxDetail } from './queries'

type Dimension = InboxDetail['dimensions'][number]

const dimension = (changes: Partial<Dimension> = {}): Dimension => ({
  dimension_key: 'career_direction',
  status: 'match',
  quality: 'strong',
  weight: 15,
  effective_weight: 13.04,
  strength: 1,
  contribution: 13,
  excluded: false,
  evidence: {
    direction: 'Billing SME',
    level: 'strong',
    job_quote: 'convergent billing platform of a large telecom operator',
    direction_quote: 'billing SME',
  },
  explanation: 'Best fit among your directions: Billing SME.',
  ...changes,
})

describe('DimensionList', () => {
  it('names the career direction that won, with both quotes', () => {
    render(<DimensionList dimensions={[dimension()]} />)
    const row = screen.getByRole('listitem')
    expect(within(row).getByText('Career direction')).toBeInTheDocument()
    expect(within(row).getByText(/fits: billing sme/i)).toBeInTheDocument()
    expect(
      within(row).getByText(/convergent billing platform of a large telecom operator/),
    ).toBeInTheDocument()
    expect(within(row).getByText(/“billing SME”/)).toBeInTheDocument()
  })

  it('leaves out a dimension that does not count, for example a job not assessed', () => {
    render(<DimensionList dimensions={[dimension({ excluded: true, weight: 0 })]} />)
    expect(screen.queryByRole('listitem')).not.toBeInTheDocument()
  })

  it('shows the other dimensions as before', () => {
    render(
      <DimensionList
        dimensions={[
          dimension({
            dimension_key: 'compensation',
            status: 'unknown',
            quality: null,
            evidence: {},
            explanation: 'The posting states no pay.',
          }),
        ]}
      />,
    )
    expect(screen.getByText('Compensation')).toBeInTheDocument()
    expect(screen.queryByText(/fits:/i)).not.toBeInTheDocument()
  })

  it('shows the board location next to the regions the text names for remote work (ADR-069)', () => {
    render(
      <DimensionList
        dimensions={[
          dimension({
            dimension_key: 'work_arrangement_location',
            status: 'mismatch',
            quality: null,
            evidence: {
              job_quote: 'This role is open to candidates based in the US and Europe.',
              source_places: ['North America', 'Remote'],
              text_regions: ['US', 'Europe'],
              job_regions: ['US'],
              your_regions: ['PT'],
            },
            explanation: 'Remote work is restricted to other regions.',
          }),
        ]}
      />,
    )
    const row = screen.getByRole('listitem')
    expect(within(row).getByText('Board location')).toBeInTheDocument()
    expect(within(row).getByText('North America, Remote')).toBeInTheDocument()
    expect(within(row).getByText('Regions in the text')).toBeInTheDocument()
    expect(within(row).getByText('US, Europe')).toBeInTheDocument()
    expect(within(row).getByText('Open from')).toBeInTheDocument()
    expect(within(row).getByText('US')).toBeInTheDocument()
  })

  it('shows no region block when the evidence has no source places', () => {
    render(
      <DimensionList
        dimensions={[
          dimension({
            dimension_key: 'work_arrangement_location',
            evidence: { job_quote: 'Remote within the EU', job_regions: ['EU'] },
          }),
        ]}
      />,
    )
    expect(screen.queryByText('Board location')).not.toBeInTheDocument()
  })
})
