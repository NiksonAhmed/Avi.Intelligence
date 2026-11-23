import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { RisksIssuesReport } from '../../api/types'
import { adminUser, mockApi, renderRoute, viewerUser } from '../../test/utils'

const months = Array.from({ length: 12 }, (_, i) => ({ month: `2026-${String(i + 1).padStart(2, '0')}`, opened: 0, closed: 0 }))
months[10] = { month: '2026-11', opened: 2, closed: 1 }

function report(overrides: Partial<RisksIssuesReport> = {}): RisksIssuesReport {
  return {
    tiles: [
      { key: 'open', label: 'Open issues', value: '2', note: '3 recorded in all', tone: 'warn' },
      { key: 'overdue', label: 'Overdue', value: '1', note: 'Oldest 6 days past due', tone: 'bad' },
    ],
    by_priority: [
      { key: 'High', label: 'High', count: 1, open: 1, overdue: 1 },
      { key: 'Normal', label: 'Normal', count: 2, open: 1, overdue: 0 },
    ],
    by_category: [{ key: 'Site', label: 'Site', count: 3, open: 2 }],
    by_site: [{ key: 's-101', label: '101 · Demo Hospital North', protocol_number: 'DEMO-ONC-301', open: 2, overdue: 1, total: 2 }],
    ageing: [{ key: '0-30', label: '0-30 days', count: 2, open: 2 }],
    trend: months,
    issues: [
      {
        id: 'a1', number: '1', protocol_number: 'DEMO-ONC-301', where: '101 · Demo Hospital North', category: 'Site',
        subcategory: 'Site Visit', priority: 'High', status: 'New', closed: false,
        description: 'Demo: chase missing ISF delegation log signatures', response: null, assignee: 'Demo CRA',
        opened_on: '2026-10-24', due_on: '2026-11-07', closed_on: null, days_open: 20, days_overdue: 6,
      },
    ],
    has_issues: true,
    study_options: [{ id: '11111111-1111-1111-1111-111111111111', label: 'DEMO-ONC-301 · Oncology study' }],
    site_options: [],
    rules: { source: 'Risks and issues as recorded in SimpleTrials.', priority: 'P', trend: 'T', ageing: 'A', overdue: 'O' },
    source: { mode: 'api', as_of: '2026-11-13T00:00:00Z', sandbox_only: false, snapshot_days: 0 },
    ...overrides,
  }
}

describe('Risks and issues report', () => {
  it('shows tiles, priority, category, trend, ageing, sites and the list', async () => {
    mockApi({ '/me': adminUser, '/reports/risks-issues': report() })
    renderRoute('/reports?tab=risks')
    expect(await screen.findByTestId('tile-open')).toHaveTextContent('2')
    expect(screen.getByTestId('tile-overdue')).toHaveTextContent('1')
    expect(screen.getByText('Oldest 6 days past due')).toBeInTheDocument()
    expect(screen.getAllByTestId('issue-priority-row')[0]).toHaveTextContent('High1 (1 open)')
    expect(screen.getByTestId('issue-category-row')).toHaveTextContent('Site3 (2 open)')
    expect(screen.getAllByTestId('issue-month')).toHaveLength(12)
    expect(screen.getByTestId('issue-site-row')).toHaveTextContent('1 overdue')
    const row = screen.getByTestId('issue-row')
    expect(row).toHaveTextContent('Demo: chase missing ISF delegation log signatures')
    expect(row).toHaveTextContent('6 days overdue')
    // Priority, category and age show; the full list is folded under More detail.
    expect(screen.getAllByTestId('issue-priority-row')[0]?.closest('details')).toBeNull()
    expect(screen.getByTestId('issue-ageing-row').closest('details')).toBeNull()
    expect(row.closest('details')).not.toHaveAttribute('open')
    expect(screen.getByRole('link', { name: /Excel/ })).toHaveAttribute('href', '/api/v1/reports/risks-issues/export.xlsx')
  })

  it('leads with a headline, shows tile trends, and a tile jumps to its chart', async () => {
    const insights = {
      headline: '1 of 2 open issues is overdue; 1 high priority.',
      detail: '1 closed in the last 30 days: median 28 days to close.',
      tone: 'bad' as const,
      trends: {
        open: { points: [5, 4, 3, 2], change: -3, change_text: '-3 since 17 Oct', tone: 'good' as const },
        overdue: { points: [], change: null, change_text: null, tone: 'neutral' as const },
      },
      history_since: '2026-10-17',
    }
    mockApi({ '/me': adminUser, '/reports/risks-issues': report({ insights }) })
    renderRoute('/reports?tab=risks')
    expect(await screen.findByTestId('report-headline')).toHaveTextContent('1 of 2 open issues is overdue; 1 high priority.')
    expect(screen.getAllByTestId('sparkline')).toHaveLength(1) // no line until there are two weeks
    expect(screen.getByTestId('trend-open')).toHaveTextContent('-3 since 17 Oct')
    expect(screen.queryByTestId('trend-overdue')).not.toBeInTheDocument()
    const scroll = vi.fn()
    Element.prototype.scrollIntoView = scroll
    await userEvent.click(screen.getByRole('button', { name: /Overdue: 1\. Show the detail/ }))
    expect(scroll).toHaveBeenCalled()
  })

  it('lets everyone sync from SimpleTrials', async () => {
    const viewer = { ...viewerUser, permissions: [...viewerUser.permissions, 'study.sync'] }
    mockApi({ '/me': viewer, '/reports/risks-issues': report() })
    renderRoute('/reports?tab=risks')
    expect(await screen.findByRole('button', { name: /Sync now/ })).toBeInTheDocument()
  })

  it('explains when SimpleTrials has no issues yet', async () => {
    mockApi({ '/me': adminUser, '/reports/risks-issues': report({ has_issues: false, issues: [], by_site: [] }) })
    renderRoute('/reports?tab=risks')
    expect(await screen.findByText('No risks or issues recorded in SimpleTrials yet')).toBeInTheDocument()
  })
})
