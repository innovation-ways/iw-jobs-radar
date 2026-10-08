import { Navigate, Route, Routes } from 'react-router'
import { AppShell } from '@/components/AppShell'
import { NotFound } from '@/pages/NotFound'
import { Placeholder } from '@/pages/Placeholder'
import { ProfileIntent } from '@/pages/ProfileIntent'
import { Sources } from '@/pages/Sources'
import { ALL_NAV } from '@/navigation'

/** Route table. Screens not built yet are placeholders (see the implementation guide). */
export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Navigate to="/inbox" replace />} />
        <Route path="/sources" element={<Sources />} />
        <Route path="/profile" element={<ProfileIntent />} />
        {ALL_NAV.filter((item) => !['/sources', '/profile'].includes(item.path)).map((item) => (
          <Route key={item.path} path={item.path} element={<Placeholder path={item.path} />} />
        ))}
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
