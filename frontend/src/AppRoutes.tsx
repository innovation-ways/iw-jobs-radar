import { Route, Routes } from 'react-router'
import { AppShell } from '@/components/AppShell'
import { About } from '@/pages/About'
import { AiPrivacy } from '@/pages/AiPrivacy'
import { Companies } from '@/pages/Companies'
import { Home } from '@/pages/Home'
import { Inbox } from '@/pages/Inbox'
import { NotFound } from '@/pages/NotFound'
import { Packs } from '@/pages/Packs'
import { Placeholder } from '@/pages/Placeholder'
import { ProfileIntent } from '@/pages/ProfileIntent'
import { Setup } from '@/pages/Setup'
import { Sources } from '@/pages/Sources'
import { Trends } from '@/pages/Trends'
import { Today } from '@/pages/Today'
import { Vocabulary } from '@/pages/Vocabulary'
import { ALL_NAV } from '@/navigation'

/** Route table. Screens not built yet are placeholders (see the implementation guide). */
export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Home />} />
        <Route path="/setup" element={<Setup />} />
        <Route path="/today" element={<Today />} />
        <Route path="/inbox" element={<Inbox />} />
        <Route path="/sources" element={<Sources />} />
        <Route path="/profile" element={<ProfileIntent />} />
        <Route path="/settings" element={<AiPrivacy />} />
        <Route path="/packs" element={<Packs />} />
        <Route path="/vocabulary" element={<Vocabulary />} />
        <Route path="/companies" element={<Companies />} />
        <Route path="/trends" element={<Trends />} />
        <Route path="/about" element={<About />} />
        {ALL_NAV.filter(
          (item) =>
            ![
              '/today',
              '/inbox',
              '/sources',
              '/profile',
              '/settings',
              '/packs',
              '/vocabulary',
              '/companies',
              '/trends',
            ].includes(item.path),
        ).map((item) => (
          <Route key={item.path} path={item.path} element={<Placeholder path={item.path} />} />
        ))}
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
