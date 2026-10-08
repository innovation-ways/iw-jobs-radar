import { Button } from '@/components/ui/button'
import { annualFromPayment, paymentFromAnnual, type PaymentsPerYear } from '@/lib/pay'
import type { IntentDefinition } from '@/features/profile/queries'
import { cn } from '@/lib/utils'

type EmployeePay = NonNullable<IntentDefinition['compensation']['employee_pay']>
type Contractor = NonNullable<IntentDefinition['compensation']['contractor_day_rate']>

/** Currencies offered in V1. Pay is only compared within one currency (ADR-042 context, D2). */
const CURRENCIES = ['EUR', 'GBP', 'USD', 'CHF', 'SEK', 'DKK', 'NOK', 'PLN', 'CAD', 'AUD']

const inputClass =
  'w-28 rounded-md border border-line-strong bg-surface px-2 py-1 text-right text-sm tabular-nums'

/** Digits typed by the owner as a number; blank or invalid input counts as 0. */
function toNumber(text: string): number {
  const value = Number(text.replace(/\D/g, ''))
  return Number.isFinite(value) ? value : 0
}

function show(value: number): string {
  return value === 0 ? '' : String(value)
}

function CurrencySelect({
  value,
  label,
  onChange,
}: {
  value: string
  label: string
  onChange: (currency: string) => void
}) {
  return (
    <label className="flex flex-col gap-1 text-xs text-ink-2">
      Currency
      <select
        aria-label={label}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="rounded-md border border-line-strong bg-surface px-2 py-1 text-sm text-ink"
      >
        {CURRENCIES.includes(value) ? null : <option value={value}>{value}</option>}
        {CURRENCIES.map((currency) => (
          <option key={currency}>{currency}</option>
        ))}
      </select>
    </label>
  )
}

interface EmployeeProps {
  value: EmployeePay | null
  onChange: (value: EmployeePay | null) => void
}

/**
 * Employee gross pay with linked monthly and yearly fields (decision D9): the yearly amount is
 * what is saved; the per-payment amount is derived from it using 12 or 14 payments per year.
 */
export function EmployeePayFields({ value, onChange }: EmployeeProps) {
  if (value === null) {
    return (
      <Button
        variant="outline"
        size="sm"
        onClick={() =>
          onChange({ currency: 'EUR', payments_per_year: 14, annual_minimum: 0, annual_target: 0 })
        }
      >
        Add employee pay expectation
      </Button>
    )
  }
  const n = value.payments_per_year as PaymentsPerYear
  const below = value.annual_target < value.annual_minimum
  const row = (kind: 'Minimum' | 'Target', field: 'annual_minimum' | 'annual_target') => (
    <>
      <span className="text-xs text-ink-2">{kind}</span>
      <input
        inputMode="numeric"
        aria-label={`${kind} per month`}
        className={inputClass}
        value={show(paymentFromAnnual(value[field], n))}
        onChange={(event) =>
          onChange({ ...value, [field]: annualFromPayment(toNumber(event.target.value), n) })
        }
      />
      <input
        inputMode="numeric"
        aria-label={`${kind} per year`}
        className={inputClass}
        value={show(value[field])}
        onChange={(event) => onChange({ ...value, [field]: toNumber(event.target.value) })}
      />
    </>
  )
  return (
    <div>
      <div className="grid grid-cols-[auto_auto_auto] items-center gap-x-3 gap-y-1.5">
        <span />
        <span className="text-right text-xs text-ink-2">Per month</span>
        <span className="text-right text-xs text-ink-2">Per year</span>
        {row('Minimum', 'annual_minimum')}
        {row('Target', 'annual_target')}
      </div>
      <div className="mt-3 flex flex-wrap items-end gap-3">
        <div
          role="group"
          aria-label="Payments per year"
          className="inline-flex rounded-md border border-line-strong"
        >
          {([12, 14] as const).map((count) => (
            <button
              key={count}
              type="button"
              aria-pressed={n === count}
              onClick={() => onChange({ ...value, payments_per_year: count })}
              className={cn(
                'border-r border-line-strong px-3 py-1 text-xs font-medium last:border-r-0',
                n === count ? 'bg-brand-soft text-brand-text' : 'text-ink-2 hover:bg-surface-2',
              )}
            >
              {count} payments
            </button>
          ))}
        </div>
        <CurrencySelect
          value={value.currency}
          label="Currency of employee pay"
          onChange={(currency) => onChange({ ...value, currency })}
        />
        <Button variant="ghost" size="sm" onClick={() => onChange(null)}>
          Remove employee pay
        </Button>
      </div>
      <p className="mt-1.5 text-xs text-ink-3">
        Edit either field and the other updates. The year amount is the one that is saved.
      </p>
      {below && (
        <p role="alert" className="mt-1 text-xs text-bad">
          The target must not be below the minimum.
        </p>
      )}
    </div>
  )
}

interface ContractorProps {
  value: Contractor | null
  onChange: (value: Contractor | null) => void
}

/** Contractor and freelance pay: a day rate only (decision D9). */
export function ContractorFields({ value, onChange }: ContractorProps) {
  if (value === null) {
    return (
      <Button
        variant="outline"
        size="sm"
        onClick={() => onChange({ currency: 'EUR', minimum: 0, target: 0 })}
      >
        Add day rate
      </Button>
    )
  }
  const below = value.target < value.minimum
  return (
    <div>
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-xs text-ink-2">
          Minimum
          <input
            inputMode="numeric"
            aria-label="Minimum day rate"
            className={inputClass}
            value={show(value.minimum)}
            onChange={(event) => onChange({ ...value, minimum: toNumber(event.target.value) })}
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-ink-2">
          Target
          <input
            inputMode="numeric"
            aria-label="Target day rate"
            className={inputClass}
            value={show(value.target)}
            onChange={(event) => onChange({ ...value, target: toNumber(event.target.value) })}
          />
        </label>
        <CurrencySelect
          value={value.currency}
          label="Currency of day rate"
          onChange={(currency) => onChange({ ...value, currency })}
        />
        <Button variant="ghost" size="sm" onClick={() => onChange(null)}>
          Remove day rate
        </Button>
      </div>
      {below && (
        <p role="alert" className="mt-1 text-xs text-bad">
          The target must not be below the minimum.
        </p>
      )}
    </div>
  )
}
