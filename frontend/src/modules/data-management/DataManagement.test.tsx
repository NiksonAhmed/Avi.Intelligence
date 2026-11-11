import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { adminUser, mockApi, renderRoute, viewerUser } from '../../test/utils'
import type { DmOverview, DmQueryDetail, DmQueryList, DmSdv, DmStatus } from './api'

const dmUser = { ...adminUser, permissions: [...adminUser.permissions, 'dm.view', 'dm.sync'] }

const status: DmStatus = {
  connections: [
    { name: 'sandbox', environment: 'sandbox', study_code: 'DEMO_IS', last_run: null, last_success_at: '2026-11-11T05:00:00Z' },
  ],
  scopes: [{ id: 'sandbox', label: 'DEMO_IS · Sandbox', environment: 'sandbox', multi: false }],
  default_scope: 'sandbox',
  can_sync: true,
  demo: false,
  site_answer_days: 5,
  approval_days: 3,
  sync_minutes: 60,
  rules: { clocks: 'Two clocks.', targets: 'Targets.', ageing: 'Ageing rule.', missing: 'Missing.', source: 'Read-only.' },
}

const overview: DmOverview = {
  scope: 'sandbox',
  multi: false,
  environment: 'sandbox',
  study_code: 'DEMO_IS',
  studies: [{ connection: 'sandbox', study_code: 'DEMO_IS' }],
  as_of: '2026-11-11T05:00:00Z',
  tiles: [
    { key: 'open_at_site', label: 'Open at site', value: 314, note: '120 over 5 working days', tone: 'bad' },
    { key: 'awaiting_approval', label: 'Answered, awaiting approval', value: 35, note: '30 over 3 working days', tone: 'bad' },
    { key: 'missing_items', label: 'Unconfirmed missing data', value: 1845, note: 'Blank fields', tone: 'warn' },
    { key: 'sdv', label: 'SDV completed (%)', value: 25, note: '40 of 160 fields verified', tone: 'info' },
  ],
  sdv: { required: 160, done: 40, percent: 25, forms_total: 24, forms_complete: 6 },
  sites: [
    { connection: 'sandbox', study_code: 'DEMO_IS', site_code: '102', site_name: 'Demo Cancer Centre', open_at_site: 3, awaiting_approval: 2, overdue: 2, oldest_days: 40, missing_items: 4, pending_forms: 3, sdv_required: 160, sdv_done: 40 },
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
  form_label: 'ECG',
  id: 'q8',
  connection: 'sandbox',
  study_code: 'DEMO_IS',
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

const list: DmQueryList = {
  queries: [query],
  total: 1,
  counts: { awaiting_approval: 1 },
  views: { attention: 262, open: 236, awaiting: 26, overdue: 262, sent_back: 1, closed: 52 },
}

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

const sdv: DmSdv = {
  scope: 'sandbox',
  multi: false,
  environment: 'sandbox',
  tiles: [
    { key: 'fields', label: 'Fields verified', value: 25, note: '40 of 160 fields (%)', tone: 'info' },
    { key: 'forms_complete', label: 'Forms fully verified', value: 6, note: 'of 24 forms needing SDV', tone: 'neutral' },
    { key: 'waiting', label: 'Waiting for SDV', value: 26, note: 'Oldest visit 60 days ago', tone: 'warn' },
    { key: 'data_review', label: 'Data reviewed', value: 25, note: '6 of 24 forms (%)', tone: 'neutral' },
  ],
  summary: { required: 160, done: 40, percent: 25, forms_total: 24, forms_complete: 6 },
  sites: [
    { connection: 'sandbox', study_code: 'DEMO_IS', site_code: '102', site_name: 'Demo Cancer Centre', required: 160, done: 40, percent: 25, forms_waiting: 26, oldest_waiting_days: 60 },
  ],
  visits: [
    { event_id: 'E01_SCR', event_name: 'Screening', required: 80, done: 40, percent: 50 },
    { event_id: 'E03_D1', event_name: 'Day 1', required: 80, done: 0, percent: 0 },
  ],
  forms: [
    {
      id: 'f1', connection: 'sandbox', study_code: 'DEMO_IS', site_code: '102', site_name: 'Demo Cancer Centre',
      subject_id: '102-003', event_name: 'Screening', event_date: '2026-09-12T00:00:00Z', form_label: 'ECG', kind: 'form',
      required: 5, done: 2, percent: 40, status: 'waiting', days_since_visit: 60, last_sdv_at: null, last_sdv_by: null,
      data_review_at: '2026-09-20T00:00:00Z', signed_at: null, locked_at: null,
    },
  ],
  total: 1,
  views: { waiting: 26, complete: 6, all: 32 },
  studies: [{ connection: 'sandbox', study_code: 'DEMO_IS' }],
  site_options: [{ id: '102', label: '102 · Demo Cancer Centre' }],
  form_options: [{ id: 'EG', label: 'EG · ECG' }],
  visit_options: [{ id: 'E01_SCR', label: 'Screening' }],
  rules: { sdv: 'SDV is counted per field.', review: 'Review rule.' },
}

const routes = {
  '/me': dmUser,
  '/data-management/status': status,
  '/data-management/overview': overview,
  '/data-management/queries': list,
  '/data-management/queries/q8': detail,
  '/data-management/sdv': sdv,
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
    await userEvent.click(within(row).getByRole('button', { name: 'Overdue 102' }))
    expect(router.state.location.search).toBe('?tab=queries&site=102&view=overdue')
    expect(await screen.findByTestId('dm-query-count')).toHaveTextContent('1 query')
    expect(
      fetchMock.mock.calls.some(
        ([u]) =>
          String(u).includes('/data-management/queries') &&
          String(u).includes('site=102') &&
          String(u).includes('state=not_closed') &&
          String(u).includes('flag=red'),
      ),
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

  it('chooses a study, and combines several studies of one environment', async () => {
    const many: DmStatus = {
      ...status,
      connections: [
        { name: 'onc', environment: 'sandbox', study_code: 'ONC_301', last_run: null, last_success_at: null },
        { name: 'cv', environment: 'sandbox', study_code: 'CV_201', last_run: null, last_success_at: null },
        { name: 'neu', environment: 'live', study_code: 'NEU_101', last_run: null, last_success_at: null },
      ],
      scopes: [
        { id: 'all-sandbox', label: 'All sandbox studies', environment: 'sandbox', multi: true },
        { id: 'onc', label: 'ONC_301 · Sandbox', environment: 'sandbox', multi: false },
        { id: 'cv', label: 'CV_201 · Sandbox', environment: 'sandbox', multi: false },
        { id: 'neu', label: 'NEU_101 · Live', environment: 'live', multi: false },
      ],
      default_scope: 'all-sandbox',
    }
    const combined: DmOverview = {
      ...overview,
      scope: 'all-sandbox',
      multi: true,
      study_code: null,
      studies: [
        { connection: 'onc', study_code: 'ONC_301' },
        { connection: 'cv', study_code: 'CV_201' },
      ],
      sites: [
        { ...overview.sites[0]!, connection: 'onc', study_code: 'ONC_301' },
        { ...overview.sites[0]!, connection: 'cv', study_code: 'CV_201' },
      ],
    }
    const fetchMock = mockApi({ ...routes, '/data-management/status': many, '/data-management/overview': combined })
    const { router } = renderRoute('/data-management')
    expect(await screen.findByTestId('dm-scope-title')).toHaveTextContent('All sandbox studies (2)')
    expect(screen.getByRole('button', { name: /Sync all/ })).toBeInTheDocument()
    const rows = await screen.findAllByTestId('dm-site-row')
    expect(rows[0]).toHaveTextContent('ONC_301')
    expect(rows[1]).toHaveTextContent('CV_201')

    // A site in a combined view keeps its study.
    await userEvent.click(within(rows[1]!).getByRole('button', { name: 'Overdue 102' }))
    expect(router.state.location.search).toBe('?tab=queries&site=cv%3A102&view=overdue')

    // Choosing one study narrows everything to it.
    await userEvent.click(screen.getByRole('combobox', { name: 'Study' }))
    await userEvent.click(await screen.findByTitle('NEU_101 · Live'))
    expect(router.state.location.search).toBe('?tab=queries&view=overdue&scope=neu')
    expect(fetchMock.mock.calls.some(([u]) => String(u).includes('/data-management/overview?scope=neu'))).toBe(true)
  })

  it('filters queries by the date they were raised', async () => {
    const fetchMock = mockApi({ ...routes })
    renderRoute('/data-management?tab=queries&from=2026-10-01&to=2026-10-31')
    expect(await screen.findByTestId('dm-active-filters')).toHaveTextContent('Raised: 01 Oct 2026 – 31 Oct 2026 (UTC)')
    expect(
      fetchMock.mock.calls.some(
        ([u]) => String(u).includes('raised_from=2026-10-01') && String(u).includes('raised_to=2026-10-31'),
      ),
    ).toBe(true)
    expect(await screen.findByTestId('dm-query-row')).toHaveTextContent('24 Oct 2026')
  })

  it('switches quick views with counts, and shows active filters as removable tags', async () => {
    const fetchMock = mockApi({ ...routes })
    const { router } = renderRoute('/data-management?tab=queries&site=102&q=QRS')
    await screen.findByTestId('dm-query-count') // counts appear once the list has loaded
    expect(screen.getByTestId('dm-view-attention')).toHaveTextContent('Needs attention262')
    expect(screen.getByTestId('dm-view-open')).toHaveTextContent('Open at site236')
    const tags = screen.getByTestId('dm-active-filters')
    expect(tags).toHaveTextContent('Site: 102 · Demo Cancer Centre')
    expect(tags).toHaveTextContent('Search: “QRS”')
    expect(screen.getByRole('button', { name: /Filters \(1\)/ })).toBeInTheDocument()

    await userEvent.click(screen.getByTestId('dm-view-awaiting'))
    expect(router.state.location.search).toBe('?tab=queries&site=102&q=QRS&view=awaiting')
    expect(fetchMock.mock.calls.some(([u]) => String(u).includes('state=awaiting_approval'))).toBe(true)

    // Removing one tag keeps the rest; "Clear all" removes every filter but keeps the view.
    await userEvent.click(within(tags).getAllByLabelText(/close/i)[0]!)
    expect(router.state.location.search).toBe('?tab=queries&q=QRS&view=awaiting')
    await userEvent.click(screen.getByRole('button', { name: 'Clear all' }))
    expect(router.state.location.search).toBe('?tab=queries&view=awaiting')
    expect(screen.queryByTestId('dm-active-filters')).not.toBeInTheDocument()
  })

  it('reports SDV completed vs required on the overview and opens the SDV tab for a site', async () => {
    mockApi({ ...routes })
    const { router } = renderRoute('/data-management')
    expect(await screen.findByTestId('dm-tile-sdv')).toHaveTextContent('25%')
    expect(screen.getByTestId('dm-sdv-figure')).toHaveTextContent('40 of 160')
    const site = screen.getByTestId('dm-sdv-overview-site')
    expect(site).toHaveTextContent('40 / 160 (25%)')
    await userEvent.click(within(site).getByRole('button', { name: /102 · Demo Cancer Centre/ }))
    expect(router.state.location.search).toBe('?tab=sdv&ssite=102')
  })

  it('shows the SDV tab: tiles, site and visit progress, and forms waiting for SDV', async () => {
    const fetchMock = mockApi({ ...routes })
    const { router } = renderRoute('/data-management?tab=sdv')
    expect(await screen.findByTestId('dm-sdv-tile-fields')).toHaveTextContent('25%')
    expect(screen.getByTestId('dm-sdv-tile-forms_complete')).toHaveTextContent('6')
    expect(screen.getByTestId('dm-sdv-site-row')).toHaveTextContent('40 / 160 (25%)')
    expect(screen.getAllByTestId('dm-sdv-visit-row')[0]).toHaveTextContent('40 / 80 (50%)')
    expect(screen.getByTestId('dm-sdv-view-waiting')).toHaveTextContent('Waiting for SDV26')
    const row = screen.getByTestId('dm-sdv-form-row')
    expect(row).toHaveTextContent('102-003')
    expect(row).toHaveTextContent('2 / 5')
    expect(row).toHaveTextContent(/20 Sept? 2026/) // data review date

    await userEvent.click(screen.getByTestId('dm-sdv-view-complete'))
    expect(router.state.location.search).toBe('?tab=sdv&sview=complete')
    expect(fetchMock.mock.calls.some(([u]) => String(u).includes('/data-management/sdv') && String(u).includes('view=complete'))).toBe(true)

    await userEvent.click(within(screen.getAllByTestId('dm-sdv-visit-row')[1]!).getByRole('button', { name: 'Day 1' }))
    expect(router.state.location.search).toBe('?tab=sdv&sview=complete&svisit=E03_D1')
    expect(await screen.findByTestId('dm-sdv-active-filters')).toHaveTextContent('Visit: E03_D1')
  })
})
