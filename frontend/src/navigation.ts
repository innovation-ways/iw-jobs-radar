import {
  Building2,
  Inbox,
  Rss,
  Settings,
  Sun,
  Tags,
  TrendingUp,
  User,
  type LucideIcon,
} from 'lucide-react'

export interface NavItem {
  path: string
  label: string
  icon: LucideIcon
  description: string
}

/** Daily-use screens. */
export const MAIN_NAV: NavItem[] = [
  {
    path: '/today',
    label: 'Today',
    icon: Sun,
    description: 'Daily digest of new and changed jobs.',
  },
  {
    path: '/inbox',
    label: 'Inbox',
    icon: Inbox,
    description: 'Triage jobs, scored against your intent.',
  },
  {
    path: '/companies',
    label: 'Companies',
    icon: Building2,
    description: 'Company dossiers and hiring activity.',
  },
  {
    path: '/trends',
    label: 'Trends',
    icon: TrendingUp,
    description: 'How demand changes over time.',
  },
]

/** Configuration screens. */
export const SETUP_NAV: NavItem[] = [
  {
    path: '/sources',
    label: 'Sources',
    icon: Rss,
    description: 'Job boards, schedule and collection status.',
  },
  {
    path: '/profile',
    label: 'Profile & intent',
    icon: User,
    description: 'Your career profile and what you are looking for.',
  },
  {
    path: '/vocabulary',
    label: 'Vocabulary',
    icon: Tags,
    description: 'The role families and sectors jobs are sorted into.',
  },
  {
    path: '/settings',
    label: 'AI & privacy',
    icon: Settings,
    description: 'Where processing happens and what leaves this machine.',
  },
]

export const ALL_NAV: NavItem[] = [...MAIN_NAV, ...SETUP_NAV]

/** The title of the page at `pathname`; unknown paths get a not-found title. */
export function titleFor(pathname: string): string {
  if (pathname === '/about') return 'About & credits'
  return ALL_NAV.find((item) => item.path === pathname)?.label ?? 'Page not found'
}
