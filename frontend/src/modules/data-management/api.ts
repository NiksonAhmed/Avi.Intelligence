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
  study_code: string | null
  last_run: DmSyncRun | null
  last_success_at: string | null
}

/** One study, or all studies of one environment (live and sandbox are never combined). */
export interface DmScope {
  id: string
  label: string
  environment: string
  multi: boolean
}

export interface DmStatus {
  connections: DmConnection[]
  scopes: DmScope[]
  default_scope: string
  can_sync: boolean
  demo: boolean
  site_answer_days: number
  approval_days: number
  sync_minutes: number
  rules: Record<string, string>
}

export interface DmOverview {
  scope: string
  multi: boolean
  environment: string
  /** The study's code for a single study; null for all studies. */
  study_code: string | null
  studies: { connection: string; study_code: string }[]
  as_of: string | null
  tiles: { key: string; label: string; value: number; note: string; tone: Tone }[]
  /** SDV completed vs required, counted per field. */
  sdv: DmSdvSummary
  sites: {
    connection: string
    study_code: string
    site_code: string
    site_name: string
    open_at_site: number
    awaiting_approval: number
    overdue: number
    oldest_days: number | null
    missing_items: number
    pending_forms: number
    sdv_required: number
    sdv_done: number
  }[]
  ageing: { label: string; open_at_site: number; awaiting_approval: number }[]
  forms: { form: string; open: number }[]
  site_options: { id: string; label: string }[]
  form_options: { id: string; label: string }[]
}

export interface DmQuery {
  /** The form, or "Visit date (no form)" for queries raised on the visit date. */
  form_label: string
  id: string
  connection: string
  study_code: string
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
  /** How many each quick view would show, given the other filters. */
  views: Record<'attention' | 'open' | 'awaiting' | 'overdue' | 'sent_back' | 'closed', number>
}

export interface DmQueryFilters {
  scope?: string
  /** One study within an all-studies scope. */
  study?: string
  state?: DmState | 'not_closed'
  site?: string
  form?: string
  flag?: 'red' | 'amber' | 'green'
  reopened?: boolean
  /** Raised on or after this day (YYYY-MM-DD, UTC). */
  raisedFrom?: string
  /** Raised on or before this day (YYYY-MM-DD, UTC). */
  raisedTo?: string
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

export function useDmOverview(scope?: string) {
  return useQuery({
    queryKey: ['dm', 'overview', scope ?? null],
    queryFn: () => apiRequest<DmOverview>(`${BASE}/overview`, { params: { scope } }),
  })
}

export function useDmQueries(filters: DmQueryFilters) {
  return useQuery({
    queryKey: ['dm', 'queries', filters],
    queryFn: () =>
      apiRequest<DmQueryList>(`${BASE}/queries`, {
        params: {
          scope: filters.scope,
          study: filters.study,
          state: filters.state,
          site: filters.site,
          form: filters.form,
          flag: filters.flag,
          reopened: filters.reopened ? 'true' : undefined,
          raised_from: filters.raisedFrom,
          raised_to: filters.raisedTo,
          search: filters.search,
          limit: '500',
        },
      }),
    placeholderData: (previous) => previous,
  })
}

export interface DmSdvSummary {
  required: number
  done: number
  percent: number | null
  forms_total: number
  forms_complete: number
}

export interface DmSdvForm {
  id: string
  connection: string
  study_code: string
  site_code: string
  site_name: string
  subject_id: string
  event_name: string | null
  event_date: string | null
  form_label: string
  kind: 'form' | 'event_date'
  required: number
  done: number
  percent: number | null
  status: 'waiting' | 'complete'
  days_since_visit: number | null
  last_sdv_at: string | null
  last_sdv_by: string | null
  data_review_at: string | null
  signed_at: string | null
  locked_at: string | null
}

export interface DmSdv {
  scope: string
  multi: boolean
  environment: string
  tiles: { key: string; label: string; value: number; note: string; tone: Tone }[]
  summary: DmSdvSummary
  sites: {
    connection: string
    study_code: string
    site_code: string
    site_name: string
    required: number
    done: number
    percent: number | null
    forms_waiting: number
    oldest_waiting_days: number | null
  }[]
  visits: { event_id: string; event_name: string; required: number; done: number; percent: number | null }[]
  forms: DmSdvForm[]
  total: number
  views: Record<'waiting' | 'complete' | 'all', number>
  studies: { connection: string; study_code: string }[]
  site_options: { id: string; label: string }[]
  form_options: { id: string; label: string }[]
  visit_options: { id: string; label: string }[]
  rules: Record<string, string>
}

export interface DmSdvFilters {
  scope?: string
  study?: string
  view?: 'waiting' | 'complete' | 'all'
  site?: string
  form?: string
  visit?: string
  visitFrom?: string
  visitTo?: string
  search?: string
}

export function useDmSdv(filters: DmSdvFilters) {
  return useQuery({
    queryKey: ['dm', 'sdv', filters],
    queryFn: () =>
      apiRequest<DmSdv>(`${BASE}/sdv`, {
        params: {
          scope: filters.scope,
          study: filters.study,
          view: filters.view,
          site: filters.site,
          form: filters.form,
          visit: filters.visit,
          visit_from: filters.visitFrom,
          visit_to: filters.visitTo,
          search: filters.search,
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

/** Syncs each study one after the other (Viedoc builds one export at a time per study). */
export function useDmSync() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: async (connections: string[]) => {
      const runs: DmSyncRun[] = []
      for (const connection of connections) {
        runs.push(
          await apiRequest<DmSyncRun>(`${BASE}/sync`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ connection }),
          }),
        )
      }
      return runs
    },
    onSuccess: () => void client.invalidateQueries({ queryKey: ['dm'] }),
  })
}
