import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { adminUser, mockApi, renderRoute, viewerUser } from '../../test/utils'
import type { DmLabs, DmMissing, DmOverview, DmQueryDetail, DmQueryList, DmSdv, DmStatus } from './api'

const dmUser = { ...adminUser, permissions: [...adminUser.permissions, 'dm.view', 'dm.sync'] }

const status: DmStatus = {
  connections: [
    { name: 'sandbox', environment: 'sandbox', study_code: 'DEMO_IS', last_run: null, last_success_at: '2026-11-11T05:00:00Z' },
  ],
  scopes: [{ id: 'sandbox', label: 'DEMO_IS · Sandbox', environment: 'sandbox', multi: false }],
  default_scope: 'sandbox',
  can_sync: true,
  can_export: true,
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
    { viedoc_state: 'Query Raised', at: '2026-10-24T09:30:00Z', user_role: null, resolution: null },
    { viedoc_state: 'Query Resolved', at: '2026-10-26T09:30:00Z', user_role: 'Study Coordinator', resolution: 'Demo answer' },
    { viedoc_state: 'Query Raised', at: '2026-11-01T09:30:00Z', user_role: 'Data Manager', resolution: null },
    { viedoc_state: 'Query Resolved', at: '2026-11-07T09:30:00Z', user_role: 'Study Coordinator', resolution: 'Demo answer' },
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
      required: 5, done: 2, percent: 40, status: 'waiting', days_since_visit: 60, last_sdv_at: null,
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

const missing: DmMissing = {
  scope: 'sandbox',
  multi: false,
  environment: 'sandbox',
  tiles: [
    { key: 'fields', label: 'Missing fields', value: 1845, note: 'Unconfirmed by the site · 30 subjects', tone: 'warn' },
    { key: 'overdue', label: 'Overdue', value: 1700, note: 'Over 5 working days (fields and forms)', tone: 'bad' },
    { key: 'pending', label: 'Pending forms', value: 527, note: 'Oldest 140 days', tone: 'warn' },
    { key: 'subjects', label: 'Subjects with gaps', value: 32, note: 'Missing fields or pending forms', tone: 'neutral' },
    { key: 'upgrades', label: 'Forms awaiting upgrade', value: 49, note: 'Waiting for a new design version', tone: 'info' },
  ],
  sites: [
    { connection: 'sandbox', study_code: 'DEMO_IS', site_code: 'U01', site_name: 'Demo Unit', fields: 1200, overdue: 1100, pending_forms: 300, upgrades: 20, oldest_days: 140 },
  ],
  visits: [{ id: 'E01_SCR', label: 'Screening', fields: 900, pending_forms: 120 }],
  forms: [{ id: 'PE', label: 'Physical Examination', fields: 400, pending_forms: 10 }],
  top_fields: [{ form_label: 'Physical Examination', item_label: 'Date of examination', subjects: 25 }],
  subjects: [{ connection: 'sandbox', study_code: 'DEMO_IS', site_code: 'U01', subject_id: 'AUU01-002', fields: 120, pending_forms: 14, oldest_days: 140 }],
  items: [
    {
      id: 'm1', kind: 'field', connection: 'sandbox', study_code: 'DEMO_IS', site_code: 'U01', site_name: 'Demo Unit',
      subject_id: 'AUU01-002', event_id: 'E01_SCR', event_name: 'Screening', event_date: '2026-06-19T00:00:00Z',
      form_id: 'PE', form_label: 'Physical Examination', item_label: 'Date of examination',
      since: '2026-06-20T09:30:00Z', days: 145, working_days: 104, flag: 'red',
    },
  ],
  total: 1845,
  views: { fields: 1845, overdue: 1700, pending: 527, upgrade: 49 },
  studies: [{ connection: 'sandbox', study_code: 'DEMO_IS' }],
  site_options: [{ id: 'U01', label: 'U01 · Demo Unit' }],
  form_options: [{ id: 'PE', label: 'PE · Physical Examination' }],
  visit_options: [{ id: 'E01_SCR', label: 'Screening' }],
  target_days: 5,
  rules: { missing: 'Missing rule.', target: 'Target rule.' },
}

const labs: DmLabs = {
  scope: 'sandbox',
  multi: false,
  environment: 'sandbox',
  tiles: [
    { key: 'reported', label: 'Results reported (%)', value: 92, note: '24 of 26 expected · 5 not done', tone: 'info' },
    { key: 'missing', label: 'Results missing', value: 2, note: 'Expected but blank', tone: 'warn' },
    { key: 'out_of_range', label: 'Out of range', value: 4, note: '3 high · 1 low', tone: 'warn' },
    { key: 'clin_sig', label: 'Clinically significant', value: 2, note: '1 without AE/MH reference', tone: 'bad' },
  ],
  analytes: [
    { form_label: 'Haematology', analyte: 'Platelets', expected: 7, reported: 6, missing: 1, not_done: 2, out_of_range: 0, clin_sig: 0, no_range: 1, no_unit: 0, missing_percent: 14.3 },
    { form_label: 'Haematology', analyte: 'Haemoglobin', expected: 8, reported: 8, missing: 0, not_done: 1, out_of_range: 1, clin_sig: 1, no_range: 1, no_unit: 1, missing_percent: 0 },
  ],
  sites: [{ connection: 'sandbox', study_code: 'DEMO_IS', site_code: '102', site_name: 'Demo Cancer Centre', reported: 9, missing: 1, out_of_range: 1, clin_sig: 1, flagged: 5 }],
  results: [
    {
      id: 'l1', connection: 'sandbox', study_code: 'DEMO_IS', site_code: '102', site_name: 'Demo Cancer Centre',
      subject_id: '102-001', event_id: 'E01_SCR', event_name: 'Screening', event_date: '2026-09-13T00:00:00Z',
      form_id: 'LBHM', form_label: 'Haematology', analyte: 'Haemoglobin', status: 'reported', out_of_range: 'low',
      evaluation: 'abnormal_cs', evaluation_label: 'Abnormal, clinically significant',
      issues: ['Out of range (low)', 'Clinically significant', 'No AE/MH reference'],
    },
  ],
  total: 11,
  views: { flagged: 11, out_of_range: 4, clin_sig: 2, missing: 2, no_evaluation: 1, no_unit: 1, no_range: 3, all: 31 },
  studies: [{ connection: 'sandbox', study_code: 'DEMO_IS' }],
  site_options: [{ id: '102', label: '102 · Demo Cancer Centre' }],
  form_options: [{ id: 'LBHM', label: 'LBHM · Haematology' }],
  visit_options: [{ id: 'E01_SCR', label: 'Screening' }],
  analyte_options: [{ id: 'Haemoglobin', label: 'Haemoglobin' }, { id: 'Platelets', label: 'Platelets' }],
  rules: { labs: 'Flags only: no values are stored.', range: 'Range rule.', evaluation: 'Evaluation rule.' },
}

const routes = {
  '/me': dmUser,
  '/data-management/status': status,
  '/data-management/overview': overview,
  '/data-management/queries': list,
  '/data-management/queries/q8': detail,
  '/data-management/sdv': sdv,
  '/data-management/missing': missing,
  '/data-management/labs': labs,
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
    expect(screen.getAllByText(/Data Manager/).length).toBeGreaterThan(0)
    expect(screen.queryByText(/Demo DM/)).not.toBeInTheDocument() // roles only, never names
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

  it('offers Excel downloads of the filtered lists to Admin and Data Manager', async () => {
    mockApi({ ...routes })
    renderRoute('/data-management?tab=queries&view=open&site=102&from=2026-10-01')
    const queries = await screen.findByTestId('dm-queries-excel')
    expect(queries).toHaveTextContent('Download Excel')
    expect(queries).toHaveAttribute(
      'href',
      '/api/v1/data-management/queries/export.xlsx?scope=sandbox&state=open_at_site&site=102&raised_from=2026-10-01',
    )
    await userEvent.click(screen.getByRole('tab', { name: 'SDV' }))
    expect(await screen.findByTestId('dm-sdv-excel')).toHaveAttribute(
      'href',
      '/api/v1/data-management/sdv/export.xlsx?scope=sandbox&view=waiting',
    )
  })

  it('hides Excel downloads from everyone else (for example CRAs)', async () => {
    mockApi({ ...routes, '/data-management/status': { ...status, can_export: false } })
    renderRoute('/data-management?tab=queries')
    expect(await screen.findByTestId('dm-query-count')).toBeInTheDocument()
    expect(screen.queryByTestId('dm-queries-excel')).not.toBeInTheDocument()
    expect(screen.queryByText('Download Excel')).not.toBeInTheDocument()
  })

  it('shows missing data: tiles, sites, worst subjects and an overdue list with Excel', async () => {
    const fetchMock = mockApi({ ...routes })
    const { router } = renderRoute('/data-management?tab=missing')
    expect(await screen.findByTestId('dm-missing-tile-fields')).toHaveTextContent('1845')
    expect(screen.getByTestId('dm-missing-tile-upgrades')).toHaveTextContent('49')
    expect(screen.getByTestId('dm-missing-site-row')).toHaveTextContent('1100')
    expect(screen.getByTestId('dm-missing-top-field')).toHaveTextContent('Date of examination · Physical Examination25 subjects')
    const row = screen.getByTestId('dm-missing-row')
    expect(row).toHaveTextContent('AUU01-002')
    expect(row).toHaveTextContent('Date of examination')
    expect(row).toHaveTextContent('Overdue')
    expect(screen.getByTestId('dm-missing-excel')).toHaveAttribute('href', '/api/v1/data-management/missing/export.xlsx?scope=sandbox&view=fields')

    await userEvent.click(screen.getByTestId('dm-missing-view-pending'))
    expect(router.state.location.search).toBe('?tab=missing&mview=pending')
    expect(fetchMock.mock.calls.some(([u]) => String(u).includes('/data-management/missing') && String(u).includes('view=pending'))).toBe(true)

    await userEvent.click(within(screen.getByTestId('dm-missing-subject-row')).getByRole('button', { name: 'AUU01-002' }))
    expect(router.state.location.search).toBe('?tab=missing&mview=pending&mq=AUU01-002')
    expect(await screen.findByTestId('dm-missing-active-filters')).toHaveTextContent('Subject: “AUU01-002”')
  })

  it('shows lab flags (no values): views, analytes and the results to check', async () => {
    mockApi({ ...routes })
    const { router } = renderRoute('/data-management?tab=labs')
    expect(await screen.findByTestId('dm-labs-tile-reported')).toHaveTextContent('92%')
    expect(screen.getByTestId('dm-labs-tile-clin_sig')).toHaveTextContent('2')
    expect(screen.getByTestId('dm-labs-view-flagged')).toHaveTextContent('To check11')
    const row = screen.getByTestId('dm-labs-row')
    expect(row).toHaveTextContent('102-001')
    expect(row).toHaveTextContent('Low')
    expect(row).toHaveTextContent('Abnormal, clinically significant')
    expect(row).toHaveTextContent('No AE/MH reference')
    expect(screen.getAllByTestId('dm-labs-analyte-row')[0]).toHaveTextContent('1 (14.3%)')
    expect(screen.getByText(/Flags only: no values are stored/)).toBeInTheDocument()

    await userEvent.click(within(screen.getAllByTestId('dm-labs-analyte-row')[0]!).getByRole('button', { name: 'Platelets' }))
    expect(router.state.location.search).toBe('?tab=labs&lanalyte=Platelets&lview=all')
    expect(await screen.findByTestId('dm-labs-excel')).toHaveAttribute(
      'href',
      '/api/v1/data-management/labs/export.xlsx?scope=sandbox&view=all&analyte=Platelets',
    )
  })
})
