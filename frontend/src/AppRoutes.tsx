import { Navigate, Route, Routes } from 'react-router'
import { AppShell } from '@/components/AppShell'
import { NotFound } from '@/pages/NotFound'
import { Placeholder } from '@/pages/Placeholder'
import { ALL_NAV } from '@/navigation'

/** Route table. Every screen is a placeholder until its task (see the implementation guide). */
export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Navigate to="/inbox" replace />} />
        {ALL_NAV.map((item) => (
          <Route key={item.path} path={item.path} element={<Placeholder path={item.path} />} />
        ))}
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
