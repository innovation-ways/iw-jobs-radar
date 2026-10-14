import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import { makeDetail, makeItem } from '@/test/inboxBuilders'
import { JobDetail } from './JobDetail'

function renderDetail(overrides: Parameters<typeof makeDetail>[1]) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <JobDetail
          detail={makeDetail(makeItem(), overrides)}
          busy={false}
          onAction={vi.fn()}
          onLinkDecision={vi.fn()}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('JobDetail original link', () => {
  it('opens the posting page, not the apply link', () => {
    renderDetail({
      source_url: 'https://board.example.test/jobs/role-acme',
      apply_url: 'https://forms.example.test/apply',
    })
    expect(screen.getByRole('link', { name: /open original/i })).toHaveAttribute(
      'href',
      'https://board.example.test/jobs/role-acme',
    )
  })

  it('falls back to the apply link when the source has no posting page', () => {
    renderDetail({ source_url: null, apply_url: 'https://forms.example.test/apply' })
    expect(screen.getByRole('link', { name: /open original/i })).toHaveAttribute(
      'href',
      'https://forms.example.test/apply',
    )
  })
})
