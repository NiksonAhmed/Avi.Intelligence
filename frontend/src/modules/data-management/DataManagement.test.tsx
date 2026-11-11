import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { adminUser, mockApi, renderRoute, viewerUser } from '../../test/utils'
import type { DmOverview, DmQueryDetail, DmQueryList, DmStatus } from './api'

const dmUser = { ...adminUser, permissions: [...adminUser.permissions, 'dm.view', 'dm.sync'] }

const status: DmStatus = {
  connections: [{ name: 'sandbox', environment: 'sandbox', last_run: null, last_success_at: '2026-11-11T05:00:00Z' }],
  can_sync: true,
  demo: false,
  site_answer_days: 5,
  approval_days: 3,
  sync_minutes: 60,
  rules: { clocks: 'Two clocks.', targets: 'Targets.', ageing: 'Ageing rule.', missing: 'Missing.', source: 'Read-only.' },
}

const overview: DmOverview = {
  connection: 'sandbox',
  environment: 'sandbox',
  study_code: 'DEMO_IS',
  as_of: '2026-11-11T05:00:00Z',
  tiles: [
    { key: 'open_at_site', label: 'Open at site', value: 314, note: '120 over 5 working days', tone: 'bad' },
    { key: 'awaiting_approval', label: 'Answered, awaiting approval', value: 35, note: '30 over 3 working days', tone: 'bad' },
    { key: 'missing_items', label: 'Unconfirmed missing data', value: 1845, note: 'Blank fields', tone: 'warn' },
  ],
  sites: [
    { site_code: '102', site_name: 'Demo Cancer Centre', open_at_site: 3, awaiting_approval: 2, over_target: 2, oldest_days: 40, missing_items: 4, pending_forms: 3 },
  ],
  ageing: [
    { label: '0-7', open_at_site: 2, awaiting_approval: 1 },
    { label: '30+', open_at_site: 1, awaiting_approval: 0 },
  ],
  forms: [{ form: 'ECG', open: 4 }],
  site_options: [{ id: '102', label: '102 · Demo Cancer Centre' }],
  form_options: [{ id: 'EG', label: 'EG · ECG' }],
}

const query = {
  id: 'q8',
  query_number: '8',
  site_code: '102',
  site_name: 'Demo Cancer Centre',
  subject_id: '102-002',
  event_name: 'Day 1',
  form_id: 'EG',
  form_name: 'ECG',
  item_label: 'QRS interval',
  query_type: 'Validation',
  edit_check: 'EG_RANGE_QRS',
  query_text: 'Please check the QRS interval.',
  state: 'awaiting_approval' as const,
  state_label: 'Answered, awaiting approval',
  viedoc_state: 'Query Resolved',
  raised_at: '2026-10-24T09:30:00Z',
  state_since: '2026-11-07T09:30:00Z',
  age_days: 18,
  clock_days: 4,
  flag: 'red' as const,
  reopen_count: 1,
  resolution: 'Demo answer',
}

const list: DmQueryList = { queries: [query], total: 1, counts: { awaiting_approval: 1 } }

const detail: DmQueryDetail = {
  ...query,
  event_id: 'E03_D1',
  item_id: 'EGORRES_QRS',
  raised_on: 'Item',
  events: [
    { viedoc_state: 'Query Raised', at: '2026-10-24T09:30:00Z', user_role: null, user_name: null, resolution: null },
    { viedoc_state: 'Query Resolved', at: '2026-10-26T09:30:00Z', user_role: 'Study Coordinator', user_name: 'Demo Coordinator', resolution: 'Demo answer' },
    { viedoc_state: 'Query Raised', at: '2026-11-01T09:30:00Z', user_role: 'Data Manager', user_name: 'Demo DM', resolution: null },
    { viedoc_state: 'Query Resolved', at: '2026-11-07T09:30:00Z', user_role: 'Study Coordinator', user_name: 'Demo Coordinator', resolution: 'Demo answer' },
  ],
}

const routes = {
  '/me': dmUser,
  '/data-management/status': status,
  '/data-management/overview': overview,
  '/data-management/queries': list,
  '/data-management/queries/q8': detail,
}

describe('Data Management', () => {
  it('appears in the menu only when switched on and allowed', async () => {
    mockApi({ ...routes })
    renderRoute('/reports')
    expect(await screen.findByRole('link', { name: 'Data Management' })).toBeInTheDocument()
  })

  it('stays out of the menu for roles without access or when switched off', async () => {
    mockApi({ '/me': viewerUser, '/data-management/status': status })
    const viewer = renderRoute('/reports')
    expect(await screen.findByRole('link', { name: 'Reports and Insights' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Data Management' })).not.toBeInTheDocument()
    viewer.unmount()

    mockApi({ '/me': dmUser }) // status answers 404: switched off
    renderRoute('/reports')
    expect(await screen.findByRole('link', { name: 'Reports and Insights' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Data Management' })).not.toBeInTheDocument()
  })

  it('shows the overview and opens the filtered query list from a site row', async () => {
    const fetchMock = mockApi({ ...routes })
    const { router } = renderRoute('/data-management')
    expect(await screen.findByTestId('dm-tile-open_at_site')).toHaveTextContent('314')
    expect(screen.getByTestId('dm-environment')).toHaveTextContent('Sandbox (test data)')
    expect(screen.getByText('DEMO_IS')).toBeInTheDocument()
    expect(screen.getAllByTestId('dm-ageing-row')).toHaveLength(2)

    const row = screen.getByTestId('dm-site-row')
    expect(row).toHaveTextContent('102 · Demo Cancer Centre')
    await userEvent.click(within(row).getByRole('button', { name: 'Over target 102' }))
    expect(router.state.location.search).toBe('?tab=queries&site=102&flag=red')
    expect(await screen.findByTestId('dm-query-count')).toHaveTextContent('1 query')
    expect(
      fetchMock.mock.calls.some(([u]) => String(u).includes('/data-management/queries') && String(u).includes('site=102') && String(u).includes('flag=red')),
    ).toBe(true)
  })

  it('shows a query timeline, including a sent-back answer', async () => {
    mockApi({ ...routes })
    renderRoute('/data-management?tab=queries')
    const row = await screen.findByTestId('dm-query-row')
    expect(row).toHaveTextContent('102-002')
    expect(row).toHaveTextContent('Us: 4 / 3 wd')
    expect(within(row).getByText('1×')).toBeInTheDocument()
    await userEvent.click(row)
    expect(await screen.findByText('Query 8')).toBeInTheDocument()
    expect(screen.getAllByText('Query Resolved')).toHaveLength(2)
    expect(screen.getByText(/Data Manager \(Demo DM\)/)).toBeInTheDocument()
    expect(screen.getByText(/answer and approve queries in Viedoc/)).toBeInTheDocument()
  })

  it('runs Sync now for allowed roles', async () => {
    const fetchMock = mockApi({
      ...routes,
      '/data-management/sync': { started_at: '2026-11-11T06:00:00Z', finished_at: '2026-11-11T06:00:30Z', ok: true, counts: { queries: 316 }, error: null, triggered_by: 'Admin' },
    })
    renderRoute('/data-management')
    await userEvent.click(await screen.findByRole('button', { name: /Sync now/ }))
    expect(await screen.findByText('Synced: 316 queries')).toBeInTheDocument()
    const sync = fetchMock.mock.calls.find(([u]) => String(u).includes('/data-management/sync'))
    expect(JSON.parse(String((sync![1] as RequestInit).body))).toEqual({ connection: 'sandbox' })
  })
})
