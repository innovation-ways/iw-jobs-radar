import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import { unwrap } from '@/api/errors'
import type { components } from '@/api/schema'

export type TrendReport = components['schemas']['TrendReportRead']
export type TrendRow = TrendReport['rows'][number]
export type TermKind = TrendReport['kind']

/** The ranked terms of one kind over the last `weeks` weeks. */
export function useTrends(kind: TermKind, weeks: number) {
  return useQuery({
    queryKey: ['trends', kind, weeks],
    placeholderData: keepPreviousData,
    queryFn: () => unwrap(api.GET('/api/v1/trends', { params: { query: { kind, weeks } } })),
  })
}
