import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router'
import { AppRoutes } from '@/AppRoutes'
import { ThemeProvider } from '@/theme/ThemeProvider'

const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 10_000 } } })

/** Application root: data fetching, theme and routing providers. */
export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </ThemeProvider>
    </QueryClientProvider>
  )
}
