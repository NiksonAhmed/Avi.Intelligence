import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { DeliveryMilestone, StudyDeliveryReport } from '../../api/types'
import { axisTicks, milestoneTone, positionPct, timelineRange } from '../../lib/reports'
import { adminUser, mockApi, renderRoute, viewerUser } from '../../test/utils'

function milestone(overrides: Partial<DeliveryMilestone> = {}): DeliveryMilestone {
  return {
    study_id: 's1',
    protocol_number: 'DEMO-ONC-301',
    name: 'First patient in',
    original_date: '2026-03-01',
    current_date: '2026-03-15',
    variance_days: 14,
    state: 'completed',
    schedule: 'slipped',
    completed_on: '2026-03-15',
    completion_basis: 'first-seen',
    on_time: false,
    ...overrides,
  }
}

function report(overrides: Partial<StudyDeliveryReport> = {}): StudyDeliveryReport {
  return {
    tiles: [
      { key: 'on_plan', label: 'Studies on plan', value: '2 of 4', note: 'No key milestone overdue', tone: 'neutral' },
      { key: 'overdue', label: 'Key milestones overdue', value: '1', note: 'Past the current end date', tone: 'bad' },
      { key: 'slipped_major', label: 'Slipped more than 30 days', value: '2', note: 'Still to complete', tone: 'bad' },
      { key: 'enrolment', label: 'Enrolled vs target', value: '84 of 145', note: '57.9%', tone: 'info' },
    ],
    milestones: [
      milestone(),
      milestone({
        name: 'Last patient in',
        original_date: '2027-03-01',
        current_date: '2027-05-06',
        variance_days: 66,
        state: 'upcoming',
        schedule: 'slipped_major',
        completed_on: null,
        completion_basis: null,
        on_time: null,
      }),
    ],
    on_time: { completed: 1, on_time: 0, with_original_date: 1 },
    sites: [
      { study_id: 's1', protocol_number: 'DEMO-ONC-301', site_id: 'a', site_number: '201', name: 'Demo Clinic Auckland', country: 'NZ', enrolled: 0, target: 40, percent: 0, flag: 'zero' },
      { study_id: 's1', protocol_number: 'DEMO-ONC-301', site_id: 'b', site_number: '101', name: 'Demo Hospital North', country: 'AU', enrolled: 31, target: 40, percent: 77.5, flag: 'none' },
      { study_id: 's4', protocol_number: 'DEMO-RES-202', site_id: 'c', site_number: '501', name: 'Demo Respiratory Clinic', country: 'AU', enrolled: 9, target: null, percent: null, flag: 'no_target' },
    ],
    activation: { total: 7, activated: 5, percent: 71.4, with_target: 5, on_time: 1 },
    pending_sites: [
      { study_id: 's2', protocol_number: 'DEMO-CV-201', site_id: 'd', site_number: '302', name: 'Demo General Hospital', status: 'Ethics submitted', planned_date: '2026-11-04', days_late: 5, state: 'late' },
    ],
    study_options: [
      { id: '11111111-1111-1111-1111-111111111111', label: 'DEMO-ONC-301 · Oncology study' },
      { id: '22222222-2222-2222-2222-222222222222', label: 'DEMO-CV-201 · Cardiology study' },
    ],
    site_options: [],
    rules: {
      schedule_slipped: 'Slipped: the current end date is later than the original end date.',
      study_on_plan: 'A study is on plan when none of its key milestones is overdue.',
      on_time: 'On time: completed on or before the original end date.',
      enrolment: 'Enrolled against target as reported by SimpleTrials.',
      activation: 'Activated: SimpleTrials has an actual activation date.',
    },
    source: { mode: 'mock', as_of: '2026-11-09T00:00:00Z', sandbox_only: false, snapshot_days: 1 },
    ...overrides,
  }
}

describe('report chart helpers', () => {
  it('spans whole months around every date and today', () => {
    const range = timelineRange([milestone()], '2026-11-09')
    expect(new Date(range.start).toISOString().slice(0, 10)).toBe('2026-03-01')
    expect(new Date(range.end).toISOString().slice(0, 10)).toBe('2026-12-01')
    expect(positionPct('2026-03-01', range)).toBe(0)
    expect(positionPct('2026-12-01', range)).toBe(100)
    const ticks = axisTicks(range, 4)
    expect(ticks[0]).toEqual({ label: 'Mar 26', pct: 0 })
    expect(ticks.length).toBeLessThanOrEqual(5)
  })

  it('labels milestones by progress first, then schedule', () => {
    expect(milestoneTone(milestone())).toEqual({ tone: 'warn', label: 'Completed +14d' })
    expect(milestoneTone(milestone({ on_time: true, variance_days: 0 }))).toEqual({ tone: 'good', label: 'Completed' })
    expect(milestoneTone(milestone({ state: 'overdue', schedule: 'slipped_major', variance_days: 40 })).label).toBe('Overdue +40d')
    expect(milestoneTone(milestone({ state: 'upcoming', schedule: 'ahead', variance_days: -15 })).label).toBe('Ahead −15d')
    expect(milestoneTone(milestone({ state: 'upcoming', schedule: 'no_baseline', variance_days: null })).label).toBe('No original date')
  })
})

describe('Reports and Insights page', () => {
  it('shows the Study delivery tiles, timeline, enrolment and activation', async () => {
    mockApi({ '/me': adminUser, '/reports/study-delivery': report() })
    renderRoute('/reports')

    expect(await screen.findByTestId('tile-on_plan')).toHaveTextContent('2 of 4')
    expect(screen.getByText('Demo data: SimpleTrials is not connected')).toBeInTheDocument()
    expect(screen.getAllByTestId('timeline-row')).toHaveLength(2)
    expect(screen.getByText('Slipped +66d')).toBeInTheDocument()
    expect(screen.getByText(/0 of 1 completed key milestones were on time/)).toBeInTheDocument()

    const rows = screen.getAllByTestId('enrolment-row')
    expect(within(rows[0]!).getByText('0 of 40 (0%)')).toBeInTheDocument()
    expect(within(rows[2]!).getByText('9 enrolled · no target recorded')).toBeInTheDocument()

    expect(screen.getByTestId('activation-figure')).toHaveTextContent('5 of 7')
    expect(screen.getByText('5 days late')).toBeInTheDocument()
    expect(screen.getByText(/Trend charts .* appear after two weeks/)).toBeInTheDocument()
  })

  it('filters by study and keeps the filter in the URL and the Excel link', async () => {
    const fetchMock = mockApi({ '/me': viewerUser, '/reports/study-delivery': report() })
    const { router } = renderRoute('/reports')
    await screen.findByTestId('tile-on_plan')

    await userEvent.click(screen.getByRole('combobox', { name: 'Filter by study' }))
    await userEvent.click(await screen.findByTitle('DEMO-CV-201 · Cardiology study'))

    expect(router.state.location.search).toBe('?study=22222222-2222-2222-2222-222222222222')
    expect(
      fetchMock.mock.calls.some(([u]) =>
        String(u).includes('/api/v1/reports/study-delivery?study_id=22222222-2222-2222-2222-222222222222'),
      ),
    ).toBe(true)
    expect(screen.getByRole('link', { name: /Excel/ })).toHaveAttribute(
      'href',
      '/api/v1/reports/study-delivery/export.xlsx?study_id=22222222-2222-2222-2222-222222222222',
    )
  })

  it('prints the report for PDF', async () => {
    const print = vi.spyOn(window, 'print').mockImplementation(() => undefined)
    mockApi({ '/me': adminUser, '/reports/study-delivery': report() })
    renderRoute('/reports')
    await screen.findByTestId('tile-on_plan')
    await userEvent.click(screen.getByRole('button', { name: /PDF/ }))
    expect(print).toHaveBeenCalled()
  })

  it('labels the SimpleTrials sandbox', async () => {
    mockApi({
      '/me': adminUser,
      '/reports/study-delivery': report({ source: { mode: 'api', as_of: '2026-11-09T00:00:00Z', sandbox_only: true, snapshot_days: 20 } }),
    })
    renderRoute('/reports')
    expect(await screen.findByText('SimpleTrials sandbox study')).toBeInTheDocument()
    expect(screen.getByText(/Source: SimpleTrials/)).toBeInTheDocument()
    expect(screen.queryByText(/Trend charts/)).not.toBeInTheDocument()
  })
})
