import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it } from 'vitest'
import { DirectionsEditor } from './DirectionsEditor'
import type { ProfileForm } from './form'

type Directions = ProfileForm['directions']

/** Holds the list the way the profile panel does, so edits flow back into the editor. */
function Harness({ initial = [] }: { initial?: Directions }) {
  const [directions, setDirections] = useState<Directions>(initial)
  return (
    <>
      <DirectionsEditor directions={directions} onChange={setDirections} />
      <output aria-label="state">{JSON.stringify(directions)}</output>
    </>
  )
}

const state = (): Directions => JSON.parse(screen.getByLabelText('state').textContent ?? '[]')
const one = { label: 'Billing SME', text: 'I look for telecom roles.', enabled: true }

describe('DirectionsEditor', () => {
  it('explains the feature and starts empty', () => {
    render(<Harness />)
    expect(screen.getByRole('heading', { name: /career directions/i })).toBeInTheDocument()
    expect(screen.getByText(/write in english/i)).toBeInTheDocument()
    expect(screen.getByText(/no directions yet/i)).toBeInTheDocument()
  })

  it('adds a blank, enabled direction with the plus button', async () => {
    render(<Harness />)
    await userEvent.click(screen.getByRole('button', { name: /add a direction/i }))
    expect(state()).toEqual([{ label: '', text: '', enabled: true }])
    expect(screen.getByLabelText(/direction label/i)).toBeInTheDocument()
  })

  it('edits the label and the text', async () => {
    render(<Harness initial={[one]} />)
    const label = screen.getByLabelText(/direction label/i)
    await userEvent.clear(label)
    await userEvent.type(label, 'AI engineer')
    await userEvent.type(screen.getByLabelText(/direction text/i), ' Also AI.')
    expect(state()[0]).toMatchObject({
      label: 'AI engineer',
      text: 'I look for telecom roles. Also AI.',
    })
  })

  it('turns a direction off and on without losing it', async () => {
    render(<Harness initial={[one]} />)
    const toggle = screen.getByRole('checkbox', { name: /judge new jobs against this/i })
    await userEvent.click(toggle)
    expect(state()[0].enabled).toBe(false)
    await userEvent.click(toggle)
    expect(state()[0].enabled).toBe(true)
  })

  it('removes a direction', async () => {
    render(<Harness initial={[one, { label: 'AI', text: 'Moving to AI.', enabled: true }]} />)
    const first = screen.getAllByRole('listitem')[0]
    await userEvent.click(within(first).getByRole('button', { name: /remove direction/i }))
    expect(state().map((d) => d.label)).toEqual(['AI'])
  })

  it('counts the characters and stops offering the plus button at five', async () => {
    const five = ['A', 'B', 'C', 'D', 'E'].map((label) => ({ ...one, label }))
    render(<Harness initial={five} />)
    expect(screen.getAllByText(/25 \/ 1,000/)).toHaveLength(5)
    expect(screen.getByRole('button', { name: /add a direction/i })).toBeDisabled()
    expect(screen.getByText(/at most 5/i)).toBeInTheDocument()
  })

  it('says new jobs only are judged and how to assess an older one', () => {
    render(<Harness initial={[one]} />)
    expect(screen.getByText(/jobs first seen after you save/i)).toBeInTheDocument()
  })
})
