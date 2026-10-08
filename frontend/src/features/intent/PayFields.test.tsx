import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it } from 'vitest'
import type { IntentDefinition } from '@/features/profile/queries'
import { ContractorFields, EmployeePayFields } from './PayFields'

type Compensation = IntentDefinition['compensation']

function Harness({ initial }: { initial: Compensation }) {
  const [value, setValue] = useState(initial)
  return (
    <>
      <EmployeePayFields
        value={value.employee_pay ?? null}
        onChange={(employee_pay) => setValue({ ...value, employee_pay })}
      />
      <ContractorFields
        value={value.contractor_day_rate ?? null}
        onChange={(contractor_day_rate) => setValue({ ...value, contractor_day_rate })}
      />
      <output data-testid="state">{JSON.stringify(value)}</output>
    </>
  )
}

const employee = {
  currency: 'EUR',
  payments_per_year: 14 as const,
  annual_minimum: 60000,
  annual_target: 75000,
}
const state = () => JSON.parse(screen.getByTestId('state').textContent!) as Compensation

describe('EmployeePayFields', () => {
  it('shows the monthly amount derived from the annual one and the other way round', async () => {
    render(
      <Harness
        initial={{ employee_pay: employee, contractor_day_rate: null, reject_below_minimum: true }}
      />,
    )
    expect(screen.getByLabelText('Minimum per year')).toHaveValue('60000')
    expect(screen.getByLabelText('Minimum per month')).toHaveValue('4286') // 60000 / 14
    const monthly = screen.getByLabelText('Target per month')
    await userEvent.clear(monthly)
    await userEvent.type(monthly, '5000')
    expect(state().employee_pay?.annual_target).toBe(70000) // 14 x 5000
    expect(screen.getByLabelText('Target per year')).toHaveValue('70000')
  })

  it('switching to 12 payments keeps the annual amount and changes the monthly one', async () => {
    render(
      <Harness
        initial={{ employee_pay: employee, contractor_day_rate: null, reject_below_minimum: true }}
      />,
    )
    await userEvent.click(screen.getByRole('button', { name: '12 payments' }))
    expect(state().employee_pay).toMatchObject({ payments_per_year: 12, annual_minimum: 60000 })
    expect(screen.getByLabelText('Minimum per month')).toHaveValue('5000')
    expect(screen.getByRole('button', { name: '12 payments' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
  })

  it('warns when the target is below the minimum', async () => {
    render(
      <Harness
        initial={{ employee_pay: employee, contractor_day_rate: null, reject_below_minimum: true }}
      />,
    )
    const target = screen.getByLabelText('Target per year')
    await userEvent.clear(target)
    await userEvent.type(target, '50000')
    expect(screen.getByRole('alert')).toHaveTextContent(/target.*minimum/i)
  })

  it('can be added and removed', async () => {
    render(
      <Harness
        initial={{ employee_pay: null, contractor_day_rate: null, reject_below_minimum: true }}
      />,
    )
    expect(screen.queryByLabelText('Minimum per year')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /add employee pay/i }))
    expect(state().employee_pay).toMatchObject({ currency: 'EUR', payments_per_year: 14 })
    await userEvent.click(screen.getByRole('button', { name: /remove employee pay/i }))
    expect(state().employee_pay).toBeNull()
  })

  it('changes the currency', async () => {
    render(
      <Harness
        initial={{ employee_pay: employee, contractor_day_rate: null, reject_below_minimum: true }}
      />,
    )
    await userEvent.selectOptions(screen.getByLabelText('Currency of employee pay'), 'GBP')
    expect(state().employee_pay?.currency).toBe('GBP')
  })
})

describe('ContractorFields', () => {
  it('edits a day rate with minimum and target', async () => {
    render(
      <Harness
        initial={{
          employee_pay: null,
          contractor_day_rate: { currency: 'EUR', minimum: 450, target: 550 },
          reject_below_minimum: true,
        }}
      />,
    )
    const minimum = screen.getByLabelText('Minimum day rate')
    await userEvent.clear(minimum)
    await userEvent.type(minimum, '500')
    expect(state().contractor_day_rate).toEqual({ currency: 'EUR', minimum: 500, target: 550 })
  })

  it('can be added with defaults', async () => {
    render(
      <Harness
        initial={{ employee_pay: null, contractor_day_rate: null, reject_below_minimum: true }}
      />,
    )
    await userEvent.click(screen.getByRole('button', { name: /add day rate/i }))
    expect(state().contractor_day_rate).toEqual({ currency: 'EUR', minimum: 0, target: 0 })
  })
})
