/** Employee pay is stored as an annual amount; the payment per period is derived (decision D9). */
export type PaymentsPerYear = 12 | 14

function whole(value: number): number {
  return Number.isFinite(value) ? Math.round(value) : 0
}

/** Annual amount for a per-payment amount (for example 14 payments of 5000 -> 70000). */
export function annualFromPayment(payment: number, payments: PaymentsPerYear): number {
  return whole(payment * payments)
}

/** Amount of one payment for an annual amount, rounded to a whole currency unit. */
export function paymentFromAnnual(annual: number, payments: PaymentsPerYear): number {
  return whole(annual / payments)
}
