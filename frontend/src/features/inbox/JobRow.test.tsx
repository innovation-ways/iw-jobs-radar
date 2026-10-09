import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { makeItem } from '@/test/inboxBuilders'
import { JobRow } from './JobRow'

function listing(source_type: string, source_name: string, id: number) {
  return {
    job_posting_id: id,
    source_type,
    source_name,
    url: `https://jobs.example.test/${id}`,
    first_seen_at: '2026-10-08T10:00:00Z',
    closed: false,
    job_opportunity_link_id: id + 100,
    link_state: 'auto' as const,
    similarity: 1,
  }
}

function renderRow(sources: ReturnType<typeof listing>[]) {
  render(<JobRow item={makeItem({ sources })} selected={false} onSelect={() => undefined} />)
}

describe('JobRow source chip', () => {
  it('names the job board a posting came from', () => {
    renderRow([listing('himalayas', 'Himalayas', 1)])
    expect(screen.getByText('via Himalayas')).toBeInTheDocument()
  })

  it('shows nothing extra for a posting that only comes from a company board', () => {
    renderRow([listing('greenhouse', 'Northwind Careers', 1)])
    expect(screen.queryByText(/^via /)).not.toBeInTheDocument()
    expect(screen.queryByText(/^also on /)).not.toBeInTheDocument()
  })

  it('says "also on" when the company board has the same job', () => {
    renderRow([listing('greenhouse', 'Northwind Careers', 1), listing('jobicy', 'Jobicy', 2)])
    expect(screen.getByText('also on Jobicy')).toBeInTheDocument()
  })

  it('lists several job boards', () => {
    renderRow([listing('jobicy', 'Jobicy', 1), listing('arbeitnow', 'Arbeitnow', 2)])
    expect(screen.getByText('via Jobicy, Arbeitnow')).toBeInTheDocument()
  })
})
