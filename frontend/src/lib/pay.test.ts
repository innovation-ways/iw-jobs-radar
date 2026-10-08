import { describe, expect, it } from 'vitest'
import { annualFromPayment, paymentFromAnnual } from './pay'

describe('linked pay fields', () => {
  it('14 payments x the payment equals the annual amount', () => {
    expect(annualFromPayment(5000, 14)).toBe(70000)
    expect(paymentFromAnnual(70000, 14)).toBe(5000)
  })

  it('12 payments divide the same annual amount differently', () => {
    expect(paymentFromAnnual(72000, 12)).toBe(6000)
    expect(annualFromPayment(6000, 12)).toBe(72000)
  })

  it('switching from 14 to 12 payments keeps the annual amount and changes the payment', () => {
    const annual = 70000
    expect(paymentFromAnnual(annual, 14)).toBe(5000)
    expect(paymentFromAnnual(annual, 12)).toBe(5833) // rounded to a whole unit; annual is unchanged
  })

  it('round-trips within rounding for any annual amount', () => {
    for (const annual of [0, 1, 30000, 59999, 75000, 123457]) {
      for (const payments of [12, 14] as const) {
        const back = annualFromPayment(paymentFromAnnual(annual, payments), payments)
        expect(Math.abs(back - annual)).toBeLessThanOrEqual(payments / 2)
      }
    }
  })

  it('treats empty or invalid input as zero', () => {
    expect(annualFromPayment(Number.NaN, 14)).toBe(0)
    expect(paymentFromAnnual(Number.NaN, 12)).toBe(0)
  })
})
