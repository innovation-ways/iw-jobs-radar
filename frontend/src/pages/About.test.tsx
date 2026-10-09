import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'
import { titleFor } from '@/navigation'
import { About } from './About'

describe('About & credits', () => {
  it('credits every data source with its licence and a link', () => {
    render(
      <MemoryRouter>
        <About />
      </MemoryRouter>,
    )
    const credits = screen.getByRole('region', { name: 'Data credits' })
    const geonames = within(credits).getByRole('link', { name: 'GeoNames' })
    expect(geonames).toHaveAttribute('href', 'https://www.geonames.org')
    expect(within(credits).getAllByText(/CC BY 4\.0/).length).toBeGreaterThan(0)
    expect(within(credits).getByRole('link', { name: 'Wikipedia' })).toHaveAttribute(
      'href',
      'https://www.wikipedia.org',
    )
    expect(within(credits).getByText(/CC BY-SA 4\.0/)).toBeInTheDocument()
    expect(within(credits).getByRole('link', { name: 'Wikidata' })).toBeInTheDocument()
    expect(within(credits).getByRole('link', { name: 'GLEIF' })).toBeInTheDocument()
    expect(within(credits).getByRole('link', { name: 'Greenhouse' })).toBeInTheDocument()
    for (const board of ['Arbeitnow', 'Jobicy', 'Himalayas', 'ITJobs.pt']) {
      expect(within(credits).getByRole('link', { name: board })).toBeInTheDocument()
    }
  })

  it('states the known limitations and where the data stays', () => {
    render(
      <MemoryRouter>
        <About />
      </MemoryRouter>,
    )
    expect(screen.getByText(/stays on this machine/i)).toBeInTheDocument()
    const limits = screen.getByRole('region', { name: 'Known limitations' })
    expect(within(limits).getByText(/no authentication/i)).toBeInTheDocument()
    expect(within(limits).getByText(/does not predict hiring/i)).toBeInTheDocument()
    expect(within(limits).getByText(/OCR/)).toBeInTheDocument()
  })

  it('has a page title', () => {
    expect(titleFor('/about')).toBe('About & credits')
  })
})
