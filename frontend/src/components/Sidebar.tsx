import { Radar } from 'lucide-react'
import { NavLink } from 'react-router'
import { ApiStatus } from '@/components/ApiStatus'
import { PipelineStatus } from '@/components/PipelineStatus'
import { MAIN_NAV, SETUP_NAV, type NavItem } from '@/navigation'
import { useNavBadges } from '@/features/today/queries'
import { cn } from '@/lib/utils'

function NavEntry({ item, badge }: { item: NavItem; badge?: { count: number; label: string } }) {
  const Icon = item.icon
  return (
    <NavLink
      to={item.path}
      className={({ isActive }) =>
        cn(
          'flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-ink-2 hover:bg-surface-2 hover:text-ink',
          isActive &&
            'bg-brand-soft font-semibold text-brand-text hover:bg-brand-soft hover:text-brand-text',
        )
      }
    >
      <Icon className="size-4 shrink-0" aria-hidden="true" />
      {item.label}
      {badge && badge.count > 0 && (
        <span
          aria-label={badge.label}
          className="ml-auto rounded-full bg-brand px-1.5 text-[11px] font-bold text-on-brand tabular-nums"
        >
          {badge.count}
        </span>
      )}
    </NavLink>
  )
}

/** Left navigation: daily screens, then setup, with backend status at the bottom. */
export function Sidebar() {
  const counts = useNavBadges()
  const badges: Record<string, { count: number; label: string }> = {
    '/today': { count: counts.today, label: `${counts.today} new on Today` },
    '/inbox': { count: counts.inbox, label: `${counts.inbox} to review in Inbox` },
    '/sources': {
      count: counts.sources,
      label: `${counts.sources} ${counts.sources === 1 ? 'source needs' : 'sources need'} attention`,
    },
  }
  return (
    <aside className="flex w-48 shrink-0 flex-col gap-1 overflow-y-auto border-r border-line bg-surface px-2.5 py-3.5">
      <div className="flex items-center gap-2.5 px-2.5 pb-3.5 pt-1.5 font-semibold tracking-tight">
        <span className="grid size-6 place-items-center rounded-[7px] bg-brand text-on-brand">
          <Radar className="size-4" aria-hidden="true" />
        </span>
        Jobs Radar
      </div>
      <nav aria-label="Main navigation" className="flex flex-col gap-1">
        {MAIN_NAV.map((item) => (
          <NavEntry key={item.path} item={item} badge={badges[item.path]} />
        ))}
        <div className="px-2.5 pb-1 pt-3.5 text-[11px] uppercase tracking-wider text-ink-3">
          Setup
        </div>
        {SETUP_NAV.map((item) => (
          <NavEntry key={item.path} item={item} badge={badges[item.path]} />
        ))}
      </nav>
      <div className="mt-auto border-t border-line px-2.5 pt-2.5">
        <ApiStatus />
        <PipelineStatus />
        <p className="mt-2 text-[11px] text-ink-3">
          <NavLink to="/about" className="underline">
            About &amp; credits
          </NavLink>
          <br />
          Place data from{' '}
          <a href="https://www.geonames.org" target="_blank" rel="noreferrer" className="underline">
            GeoNames
          </a>{' '}
          (CC BY 4.0)
        </p>
      </div>
    </aside>
  )
}
