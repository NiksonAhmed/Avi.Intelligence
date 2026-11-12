import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { QualityReport, QualityScheduleRow } from '../../api/types'
import { adminUser, mockApi, renderRoute, viewerUser } from '../../test/utils'

function row(overrides: Partial<QualityScheduleRow> = {}): QualityScheduleRow {
  return {
    id: 'demo-sop-001',
    sop_number: 'SOP-001',
    title: 'Document Control and SOP Management',
    version: '4.0',
    department: 'Quality Assurance',
    owner: 'Head of Quality',
    effective_date: '2024-02-01',
    review_date: '2026-02-01',
    days_to_review: -281,
    state: 'overdue',
    forms: 0,
    open_tasks: 1,
    ...overrides,
  }
}

function report(overrides: Partial<QualityReport> = {}): QualityReport {
  const months = ['Nov 26', 'Dec 26', 'Jan 27', 'Feb 27', 'Mar 27', 'Apr 27', 'May 27', 'Jun 27', 'Jul 27', 'Aug 27', 'Sep 27', 'Oct 27']
  return {
    tiles: [
      { key: 'approved', label: 'Approved SOPs', value: '11', note: '3 forms and templates', tone: 'neutral' },
      { key: 'review_overdue', label: 'Reviews overdue', value: '6', note: 'Review date has passed', tone: 'bad' },
      { key: 'review_due_soon', label: 'Reviews due in 30 days', value: '1', note: 'Plan the review now', tone: 'warn' },
      { key: 'changes', label: 'Changes in the last 12 months', value: '1', note: '1 documents', tone: 'info' },
      { key: 'health', label: 'Documents with findings', value: '1', note: 'of 18 listed', tone: 'warn' },
    ],
    schedule: [
      row(),
      row({ id: 'demo-sop-011', sop_number: 'SOP-011', title: 'Site Initiation', review_date: '2026-11-20', days_to_review: 11, state: 'due_soon', forms: 2, open_tasks: 0 }),
    ],
    by_month: [
      { key: 'overdue', label: 'Overdue', count: 6, items: ['SOP-001', 'SOP-002'] },
      ...months.map((label, i) => ({ key: `m${i}`, label, count: i === 0 ? 1 : 0, items: i === 0 ? ['SOP-011'] : [] })),
    ],
    later: 2,
    health: [
      { key: 'no_review_date', label: 'No review date', description: 'Approved SOPs with no review date.', count: 0, items: [] },
      {
        key: 'version_mismatch',
        label: 'File name and document disagree on the version',
        description: 'The file name states a different version.',
        count: 1,
        items: [{ id: 'demo-sop-012', label: 'SOP-012 · Monitoring' }],
      },
    ],
    changes: [
      {
        id: 'demo-sop-012',
        sop_number: 'SOP-012',
        title: 'Monitoring',
        kind: 'sop',
        version: '5.0',
        issued: '2026-03-10',
        changes: 'Added remote monitoring visits',
        basis: 'history',
      },
    ],
    months: 12,
    department_options: [
      { id: 'Clinical Operations', label: 'Clinical Operations' },
      { id: 'Quality Assurance', label: 'Quality Assurance' },
    ],
    rules: { review: 'Next review: the review date in SharePoint.', health: 'Library health.', change_log: 'Changes.', tasks: 'Open review tasks.' },
    source: { mode: 'mock', approved_only: false, library: 'Documents' },
    fetched_at: '2026-11-09T00:00:00Z',
    ...overrides,
  }
}

describe('Quality (SOPs) report', () => {
  it('shows tiles, reviews by month, the schedule, library health and the change log', async () => {
    mockApi({ '/me': adminUser, '/reports/quality': report() })
    renderRoute('/reports?tab=quality')

    expect(await screen.findByTestId('tile-review_overdue')).toHaveTextContent('6')
    expect(screen.getByText('Demo data: SharePoint is not connected')).toBeInTheDocument()

    const months = screen.getAllByTestId('review-month')
    expect(months).toHaveLength(13)
    expect(within(months[0]!).getByRole('img')).toHaveAccessibleName('Overdue: 6 reviews (SOP-001, SOP-002)')
    expect(screen.getByText('2 more reviews due after these 12 months.')).toBeInTheDocument()

    const rows = screen.getAllByTestId('schedule-row')
    expect(rows[0]).toHaveTextContent('Overdue 281d')
    expect(rows[1]).toHaveTextContent('Due in 11d')
    expect(rows[1]).toHaveTextContent('2 forms')
    expect(within(rows[0]!).getByRole('link', { name: 'SOP-001 · Document Control and SOP Management' })).toHaveAttribute(
      'href',
      '/documents/sops/demo-sop-001',
    )

    // Checks with findings are listed first.
    expect(screen.getByTestId('health-version_mismatch')).toHaveTextContent('SOP-012 · Monitoring')
    expect(screen.getByTestId('health-no_review_date')).toHaveTextContent('None')

    expect(screen.getByTestId('change-row')).toHaveTextContent('Added remote monitoring visits')
  })

  it('filters by department and period, in the URL and the Excel link', async () => {
    const fetchMock = mockApi({ '/me': viewerUser, '/reports/quality': report() })
    const { router } = renderRoute('/reports?tab=quality')
    await screen.findByTestId('tile-approved')

    await userEvent.click(screen.getByRole('combobox', { name: 'Filter by department' }))
    await userEvent.click(await screen.findByTitle('Quality Assurance'))
    await userEvent.click(screen.getByRole('combobox', { name: 'Change log period' }))
    await userEvent.click(await screen.findByTitle('Last 24 months'))

    expect(router.state.location.search).toBe('?tab=quality&department=Quality+Assurance&months=24')
    expect(
      fetchMock.mock.calls.some(([u]) => String(u).includes('/api/v1/reports/quality?department=Quality+Assurance&months=24')),
    ).toBe(true)
    expect(screen.getByRole('link', { name: /Excel/ })).toHaveAttribute(
      'href',
      '/api/v1/reports/quality/export.xlsx?department=Quality+Assurance&months=24',
    )
  })

  it('says so when nothing changed in the period', async () => {
    mockApi({ '/me': adminUser, '/reports/quality': report({ changes: [], months: 3 }) })
    renderRoute('/reports?tab=quality&months=3')
    expect(await screen.findByText('No changes in the last 3 months.')).toBeInTheDocument()
  })

  it('syncs the SOP library from SharePoint for everyone', async () => {
    const fetchMock = mockApi({ '/me': viewerUser, '/reports/quality': report(), '/sops/refresh': null })
    renderRoute('/reports?tab=quality')
    await screen.findByTestId('tile-review_overdue')
    await userEvent.click(screen.getByRole('button', { name: /Sync now/ }))
    expect(await screen.findByText('Synced from SharePoint')).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([u, i]) => String(u).includes('/sops/refresh') && i?.method === 'POST')).toBe(true)
  })
})
