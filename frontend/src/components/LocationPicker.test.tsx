import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { LocationPicker } from './LocationPicker'

const search = vi.fn()
vi.mock('@/features/profile/queries', () => ({
  searchPlaces: (...args: unknown[]) => search(...args),
}))

const lisbon = {
  label: 'Lisbon, Portugal',
  city: 'Lisbon',
  country: 'PT',
  latitude: 38.72509,
  longitude: -9.1498,
  timezone: 'Europe/Lisbon',
  population: 517802,
}

function renderPicker(onSelect = vi.fn(), value = '') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <LocationPicker label="Base place" value={value} onSelect={onSelect} />
    </QueryClientProvider>,
  )
  return onSelect
}

describe('LocationPicker', () => {
  beforeEach(() => {
    search.mockReset()
    search.mockResolvedValue([lisbon])
  })

  it('shows the current place', () => {
    renderPicker(vi.fn(), 'Lisbon, Portugal')
    expect(screen.getByRole('combobox', { name: 'Base place' })).toHaveValue('Lisbon, Portugal')
  })

  it('searches after two characters and lists the matches', async () => {
    renderPicker()
    const box = screen.getByRole('combobox', { name: 'Base place' })
    await userEvent.type(box, 'l')
    expect(search).not.toHaveBeenCalled()
    await userEvent.type(box, 'is')
    expect(await screen.findByRole('option', { name: /Lisbon, Portugal/ })).toBeInTheDocument()
    expect(search).toHaveBeenLastCalledWith('lis')
  })

  it('selecting a match reports the resolved place with its coordinates and time zone', async () => {
    const onSelect = renderPicker()
    await userEvent.type(screen.getByRole('combobox', { name: 'Base place' }), 'lis')
    await userEvent.click(await screen.findByRole('option', { name: /Lisbon, Portugal/ }))
    expect(onSelect).toHaveBeenCalledWith(lisbon)
    expect(screen.queryByRole('option')).not.toBeInTheDocument()
  })

  it('can be used with the keyboard', async () => {
    const onSelect = renderPicker()
    const box = screen.getByRole('combobox', { name: 'Base place' })
    await userEvent.type(box, 'lis')
    await screen.findByRole('option', { name: /Lisbon/ })
    await userEvent.keyboard('{ArrowDown}{Enter}')
    expect(onSelect).toHaveBeenCalledWith(lisbon)
  })

  it('says when nothing matches', async () => {
    search.mockResolvedValue([])
    renderPicker()
    await userEvent.type(screen.getByRole('combobox', { name: 'Base place' }), 'zzz')
    expect(await screen.findByText(/no matching city/i)).toBeInTheDocument()
  })
})
