import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { RiskHeatCell, WorkManagementReport } from '../../api/types'
import { adminUser, mockApi, renderRoute, viewerUser } from '../../test/utils'

function heatMap(): RiskHeatCell[] {
  const cells: RiskHeatCell[] = []
  for (const likelihood of [3, 2, 1]) {
    for (const impact of [1, 2, 3]) {
      const score = likelihood * impact
      cells.push({
        likelihood,
        impact,
        score,
        rating: score >= 6 ? 'High' : score >= 3 ? 'Medium' : 'Low',
        risks: likelihood === 3 && impact === 3 ? 2 : 0,
        issues: likelihood === 3 && impact === 2 ? 1 : 0,
      })
    }
  }
  return cells
}

function report(overrides: Partial<WorkManagementReport> = {}): WorkManagementReport {
  return {
    tiles: [
      { key: 'open', label: 'Open tasks', value: '4', note: '1 blocked', tone: 'neutral' },
      { key: 'overdue', label: 'Overdue tasks', value: '2', note: 'Past the due date', tone: 'bad' },
      { key: 'due_soon', label: 'Due in the next 14 days', value: '1', note: 'Still open', tone: 'warn' },
      { key: 'completed', label: 'Completed in the last 30 days', value: '1', note: '1 of 1 on time', tone: 'info' },
      { key: 'high_risks', label: 'Open high risks and issues', value: '3', note: '3 open in all', tone: 'bad' },
    ],
    by_category: [
      { key: 'study', label: 'Study', not_started: 2, in_progress: 1, blocked: 0, overdue: 1, total: 3 },
      { key: 'vendor', label: 'Vendor', not_started: 0, in_progress: 0, blocked: 1, overdue: 1, total: 1 },
    ],
    by_study: [{ key: 's1', label: 'DEMO-ONC-301', not_started: 1, in_progress: 1, blocked: 0, overdue: 1, total: 2 }],
    by_person: [
      { person_id: 'demo-cra-2', name: 'Demo CRA Two', open: 2, overdue: 2, due_soon: 0, blocked: 1 },
      { person_id: 'demo-cra-1', name: 'Demo CRA One', open: 1, overdue: 0, due_soon: 1, blocked: 0 },
    ],
    overdue: [
      {
        task_id: 't1',
        reference: 'TSK-0001',
        title: 'Chase ethics approval',
        category: 'study',
        category_label: 'Study',
        about: 'DEMO-ONC-301',
        due_date: '2026-11-04',
        days_overdue: 5,
        status: 'In progress',
        waiting_on: ['Demo CRA Two'],
      },
    ],
    heat_map: heatMap(),
    top_risks: [
      {
        risk_id: 'r1',
        reference: 'RSK-0001',
        kind: 'risk',
        title: 'Slow recruitment at site 101',
        protocol_number: 'DEMO-ONC-301',
        likelihood: 3,
        impact: 3,
        score: 9,
        rating: 'High',
        owner_name: 'Demo PM One',
        status: 'Open',
      },
    ],
    completed: { total: 1, with_due_date: 1, on_time: 1 },
    study_options: [{ id: '11111111-1111-1111-1111-111111111111', label: 'DEMO-ONC-301 · Oncology study' }],
    category_options: [
      { id: 'study', label: 'Study' },
      { id: 'sop', label: 'Procedures and SOPs' },
      { id: 'vendor', label: 'Vendor' },
      { id: 'system', label: 'Computer system' },
      { id: 'general', label: 'General' },
    ],
    rules: {
      open: 'Open: not completed and not cancelled.',
      task_overdue: 'Overdue: the due date has passed.',
      due_soon: 'Due soon: within 14 days.',
      completed: 'Completed in the last 30 days: the day the last person finished.',
      by_person: "Each person's open parts.",
      heat_map: 'Score: likelihood × impact.',
      filters: 'The category filter applies to tasks only.',
    },
    source: { mode: 'mock', as_of: '2026-11-09T00:00:00Z', sandbox_only: false, snapshot_days: 0 },
    ...overrides,
  }
}

describe('Work management report', () => {
  it('shows tiles, tasks by category, study and person, overdue tasks and the heat map', async () => {
    mockApi({ '/me': adminUser, '/reports/work-management': report() })
    renderRoute('/reports?tab=work')

    expect(await screen.findByTestId('tile-overdue')).toHaveTextContent('2')
    expect(screen.getByTestId('tile-high_risks')).toHaveTextContent('3')

    const cats = screen.getAllByTestId('category-row')
    expect(cats).toHaveLength(2)
    expect(within(cats[0]!).getByText('1 overdue', { exact: false })).toBeInTheDocument()
    expect(
      within(cats[0]!).getByRole('img', {
        name: 'Study: 3 open tasks (2 not started, 1 in progress, 0 blocked), 1 overdue',
      }),
    ).toBeInTheDocument()
    expect(screen.getAllByTestId('study-row')[0]).toHaveTextContent('DEMO-ONC-301')

    const people = screen.getAllByTestId('person-row')
    expect(people[0]).toHaveTextContent('Demo CRA Two')
    expect(within(people[0]!).getByRole('img').getAttribute('aria-label')).toContain('2 overdue')

    const overdue = screen.getByTestId('overdue-row')
    expect(overdue).toHaveTextContent('TSK-0001 · Chase ethics approval')
    expect(overdue).toHaveTextContent('Waiting on Demo CRA Two')
    expect(within(overdue).getByText('5 days late')).toBeInTheDocument()

    expect(screen.getByTestId('heat-3-3')).toHaveTextContent('2')
    expect(screen.getByTestId('heat-3-3')).toHaveTextContent('2 risks')
    expect(screen.getByTestId('heat-3-2')).toHaveTextContent('1 issue')
    expect(screen.getByTestId('heat-1-1')).toHaveTextContent('Low · 1')
    expect(screen.getByText('High · 9')).toBeInTheDocument()
  })

  it('filters by category, hides the study chart for other categories and updates the Excel link', async () => {
    const fetchMock = mockApi({ '/me': viewerUser, '/reports/work-management': report() })
    const { router } = renderRoute('/reports?tab=work')
    await screen.findByTestId('tile-open')

    await userEvent.click(screen.getByRole('combobox', { name: 'Filter by task category' }))
    await userEvent.click(await screen.findByTitle('Vendor'))

    expect(router.state.location.search).toBe('?tab=work&category=vendor')
    expect(
      fetchMock.mock.calls.some(([u]) => String(u).includes('/api/v1/reports/work-management?category=vendor')),
    ).toBe(true)
    expect(screen.queryByText('Open study tasks by study')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Excel/ })).toHaveAttribute(
      'href',
      '/api/v1/reports/work-management/export.xlsx?category=vendor',
    )
  })

  it('says so when nothing is overdue or open', async () => {
    mockApi({
      '/me': adminUser,
      '/reports/work-management': report({ overdue: [], by_person: [], top_risks: [] }),
    })
    renderRoute('/reports?tab=work')
    expect(await screen.findByText('No overdue tasks in this selection.')).toBeInTheDocument()
    expect(screen.getByText('Nobody has open tasks in this selection.')).toBeInTheDocument()
    expect(screen.getByText('No open risks or issues.')).toBeInTheDocument()
  })
})
