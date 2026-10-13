import { Link } from 'react-router'

/** Shown for any unknown route. */
export function NotFound() {
  return (
    <div className="mx-auto max-w-3xl px-4 sm:px-6 py-8">
      <p className="text-ink-2">
        There is nothing at this address.{' '}
        <Link to="/inbox" className="text-brand-text underline">
          Go to the inbox
        </Link>
        .
      </p>
    </div>
  )
}
