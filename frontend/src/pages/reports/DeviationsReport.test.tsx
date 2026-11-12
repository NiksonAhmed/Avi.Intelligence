import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { DeviationsReport } from '../../api/types'
import { adminUser, mockApi, renderRoute, viewerUser } from '../../test/utils'

const months = Array.from({ length: 12 }, (_, i) => ({ month: `2026-${String(i + 1).padStart(2, '0')}`, critical: 0, major: 0, minor: 0, other: 0 }))
months[10] = { month: '2026-11', critical: 1, major: 0, minor: 1, other: 0 }

function report(overrides: Partial<DeviationsReport> = {}): DeviationsReport {
  return {
    tiles: [
      { key: 'total', label: 'Protocol deviations', value: '8', note: '3 in the last 30 days', tone: 'info' },
      { key: 'open', label: 'Open', value: '5', note: 'Oldest open 85 days', tone: 'warn' },
      { key: 'major', label: 'Major or critical', value: '3', note: '3 still open', tone: 'bad' },
      { key: 'rate', label: 'Per 10 enrolled subjects', value: '1.2', note: '8 deviations, 66 subjects enrolled', tone: 'neutral' },
    ],
    by_severity: [
      { key: 'Critical', label: 'Critical', count: 1, open: 1 },
      { key: 'Major', label: 'Major', count: 2, open: 2 },
      { key: 'Minor', label: 'Minor', count: 5, open: 2 },
    ],
    by_category: [{ key: 'Visit schedule', label: 'Visit schedule', count: 3, open: 2 }],
    by_site: [
      { key: 'site-102', label: '102 · Demo Cancer Centre', protocol_number: 'DEMO-ONC-301', total: 3, open: 3, major: 2, enrolled: 20, per_10: 1.5 },
    ],
    trend: months,
    ageing: [
      { key: '0-30', label: '0-30 days', count: 2, open: 2 },
      { key: 'Over 90', label: 'Over 90 days', count: 1, open: 1 },
    ],
    deviations: [
      {
        id: 'd1', number: 'PD-006', protocol_number: 'DEMO-ONC-301', where: '102 · Demo Cancer Centre', category: 'Investigational product',
        severity: 'Critical', status: 'Open', closed: false, description: 'Demo: IP stored too warm', subject_level: false,
        occurred_on: '2026-10-31', identified_on: '2026-11-01', reported_on: '2026-11-03', closed_on: null, reportable: true,
        days_open: 11, days_to_identify: 1,
      },
    ],
    has_deviations: true,
    study_options: [{ id: '11111111-1111-1111-1111-111111111111', label: 'DEMO-ONC-301 · Oncology study' }],
    site_options: [],
    rules: { source: 'Protocol deviations as recorded in SimpleTrials.', severity: 'Severity rule.', rate: 'Rate rule.', trend: 'Trend rule.', ageing: 'Ageing rule.' },
    source: { mode: 'api', as_of: '2026-11-12T00:00:00Z', sandbox_only: false, snapshot_days: 0 },
    ...overrides,
  }
}

describe('Protocol deviations report', () => {
  it('shows tiles, severity, category, trend, ageing, sites and the list', async () => {
    mockApi({ '/me': adminUser, '/reports/deviations': report() })
    renderRoute('/reports?tab=deviations')

    expect(await screen.findByTestId('tile-total')).toHaveTextContent('8')
    expect(screen.getByTestId('tile-major')).toHaveTextContent('3')
    expect(screen.getAllByTestId('deviation-severity-row')[0]).toHaveTextContent('Critical1 (1 open)')
    expect(screen.getByTestId('deviation-category-row')).toHaveTextContent('Visit schedule3 (2 open)')
    expect(screen.getAllByTestId('deviation-month')).toHaveLength(12)
    expect(screen.getAllByTestId('deviation-ageing-row')[1]).toHaveTextContent('Over 90 days1')
    expect(screen.getByTestId('deviation-site-row')).toHaveTextContent('1.5 per 10 enrolled')
    const row = screen.getByTestId('deviation-row')
    expect(row).toHaveTextContent('PD-006')
    expect(row).toHaveTextContent('Demo: IP stored too warm')
    expect(row).toHaveTextContent('Reportable to ethics')
    expect(row).toHaveTextContent('11 days open')
  })

  it('filters by study, in the URL and the Excel link', async () => {
    mockApi({ '/me': viewerUser, '/reports/deviations': report() })
    const { router } = renderRoute('/reports?tab=deviations')
    await screen.findByTestId('tile-open')
    await userEvent.click(screen.getByRole('combobox', { name: 'Filter by study' }))
    await userEvent.click(await screen.findByTitle('DEMO-ONC-301 · Oncology study'))
    expect(router.state.location.search).toBe('?tab=deviations&study=11111111-1111-1111-1111-111111111111')
    expect(screen.getByRole('link', { name: /Excel/ })).toHaveAttribute(
      'href',
      '/api/v1/reports/deviations/export.xlsx?study_id=11111111-1111-1111-1111-111111111111',
    )
  })

  it('explains when SimpleTrials has no deviations yet', async () => {
    mockApi({ '/me': adminUser, '/reports/deviations': report({ has_deviations: false, deviations: [], by_site: [] }) })
    renderRoute('/reports?tab=deviations')
    expect(await screen.findByText('No protocol deviations recorded in SimpleTrials yet')).toBeInTheDocument()
  })
})
