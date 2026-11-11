/**
 * Data Management module (Viedoc): API types and data hooks.
 *
 * Self-contained: the rest of the app only reaches this module through its menu entry and route.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { ApiError, apiRequest } from '../../api/client'

export type DmState = 'open_at_site' | 'awaiting_approval' | 'closed'
export type DmFlag = 'red' | 'amber' | 'green' | 'none'
export type Tone = 'good' | 'info' | 'warn' | 'bad' | 'neutral'

export interface DmSyncRun {
  started_at: string
  finished_at: string | null
  ok: boolean
  counts: Record<string, string | number>
  error: string | null
  triggered_by: string
}

export interface DmConnection {
  name: string
  /** sandbox, live or demo */
  environment: string
  last_run: DmSyncRun | null
  last_success_at: string | null
}

export interface DmStatus {
  connections: DmConnection[]
  can_sync: boolean
  demo: boolean
  site_answer_days: number
  approval_days: number
  sync_minutes: number
  rules: Record<string, string>
}

export interface DmOverview {
  connection: string
  environment: string
  study_code: string | null
  as_of: string | null
  tiles: { key: string; label: string; value: number; note: string; tone: Tone }[]
  sites: {
    site_code: string
    site_name: string
    open_at_site: number
    awaiting_approval: number
    over_target: number
    oldest_days: number | null
    missing_items: number
    pending_forms: number
  }[]
  ageing: { label: string; open_at_site: number; awaiting_approval: number }[]
  forms: { form: string; open: number }[]
  site_options: { id: string; label: string }[]
  form_options: { id: string; label: string }[]
}

export interface DmQuery {
  id: string
  query_number: string
  site_code: string
  site_name: string
  subject_id: string
  event_name: string | null
  form_id: string | null
  form_name: string | null
  item_label: string | null
  query_type: string
  edit_check: string | null
  query_text: string | null
  state: DmState
  state_label: string
  viedoc_state: string
  raised_at: string | null
  state_since: string | null
  age_days: number | null
  clock_days: number | null
  flag: DmFlag
  reopen_count: number
  resolution: string | null
}

export interface DmQueryDetail extends DmQuery {
  event_id: string | null
  item_id: string | null
  raised_on: string | null
  events: { viedoc_state: string; at: string | null; user_role: string | null; user_name: string | null; resolution: string | null }[]
}

export interface DmQueryList {
  queries: DmQuery[]
  total: number
  counts: Partial<Record<DmState, number>>
}

export interface DmQueryFilters {
  connection?: string
  state?: DmState | 'not_closed'
  site?: string
  form?: string
  flag?: 'red' | 'amber' | 'green'
  reopened?: boolean
  search?: string
}

const BASE = '/data-management'

/** The module's status, or null when Data Management is switched off (the API answers 404). */
export function useDmStatus(enabled = true) {
  return useQuery({
    enabled,
    queryKey: ['dm', 'status'],
    queryFn: async () => {
      try {
        return await apiRequest<DmStatus>(`${BASE}/status`)
      } catch (err) {
        if (err instanceof ApiError && (err.status === 404 || err.status === 403)) return null
        throw err
      }
    },
    staleTime: 60_000,
  })
}

export function useDmOverview(connection?: string) {
  return useQuery({
    queryKey: ['dm', 'overview', connection ?? null],
    queryFn: () => apiRequest<DmOverview>(`${BASE}/overview`, { params: { connection } }),
  })
}

export function useDmQueries(filters: DmQueryFilters) {
  return useQuery({
    queryKey: ['dm', 'queries', filters],
    queryFn: () =>
      apiRequest<DmQueryList>(`${BASE}/queries`, {
        params: {
          connection: filters.connection,
          state: filters.state,
          site: filters.site,
          form: filters.form,
          flag: filters.flag,
          reopened: filters.reopened ? 'true' : undefined,
          search: filters.search,
          limit: '500',
        },
      }),
    placeholderData: (previous) => previous,
  })
}

export function useDmQuery(id: string | null) {
  return useQuery({
    enabled: Boolean(id),
    queryKey: ['dm', 'query', id],
    queryFn: () => apiRequest<DmQueryDetail>(`${BASE}/queries/${encodeURIComponent(id ?? '')}`),
  })
}

export function useDmSync() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (connection: string) =>
      apiRequest<DmSyncRun>(`${BASE}/sync`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ connection }),
      }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ['dm'] }),
  })
}
