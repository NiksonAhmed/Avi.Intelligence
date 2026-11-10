import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { EtmfCompleteness, EtmfReport } from '../../api/types'
import { completenessTone } from '../../lib/reports'
import { adminUser, mockApi, renderRoute, viewerUser } from '../../test/utils'

function c(key: string, label: string, filed: number, expected: number): EtmfCompleteness {
  return { key, label, expected, filed, missing: expected - filed, percent: expected ? Math.round((filed / expected) * 1000) / 10 : null }
}

function report(overrides: Partial<EtmfReport> = {}): EtmfReport {
  return {
    tiles: [
      { key: 'completeness', label: 'eTMF completeness', value: '74.8%', note: '86 of 115 expected documents filed', tone: 'info' },
      { key: 'missing', label: 'Missing documents', value: '29', note: 'Expected (placeholder) but not yet filed', tone: 'warn' },
      { key: 'on_time', label: 'Filed within 5 working days', value: '46 of 76', note: '10 filed without a document date', tone: 'neutral' },
      { key: 'expiring', label: 'Expired or expiring in 60 days', value: '2', note: '1 already expired', tone: 'bad' },
    ],
    overall: c('all', 'All documents', 86, 115),
    by_study: [c('s1', 'DEMO-ONC-301', 41, 45), c('s2', 'DEMO-CV-201', 13, 32)],
    sites_missing: [c('site-301', '301 · Demo Heart Institute (DEMO-CV-201)', 4, 13)],
    sections: ['01. General Site Documents', '02. Site Personnel'],
    heat_map: [
      {
        site_id: 'site-301',
        label: '301 · Demo Heart Institute',
        protocol_number: 'DEMO-CV-201',
        cells: [c('01. General Site Documents', '01. General Site Documents', 0, 2), c('02. Site Personnel', '02. Site Personnel', 0, 0)],
      },
    ],
    qc: [
      { label: 'Approved', count: 36 },
      { label: 'Rejected', count: 9 },
      { label: 'No QC recorded', count: 20 },
    ],
    timeliness: [
      { key: 'on_time', label: 'Within 5 working days', count: 46 },
      { key: 'late_10', label: '6–10 working days', count: 30 },
      { key: 'no_date', label: 'No document date', count: 10 },
    ],
    timeliness_measured: 76,
    timeliness_on_time: 46,
    expiring: [
      { id: 'e1', name: 'Medical Licence', protocol_number: 'DEMO-CV-201', where: '301 · Demo Heart Institute', expires_on: '2026-10-28', days: -12, state: 'expired' },
      { id: 'e2', name: 'Principal Investigator GCP Certificate', protocol_number: 'DEMO-ONC-301', where: 'Study level', expires_on: '2026-11-27', days: 18, state: 'expiring' },
    ],
    missing_documents: [],
    has_documents: true,
    study_options: [{ id: '11111111-1111-1111-1111-111111111111', label: 'DEMO-ONC-301 · Oncology study' }],
    site_options: [],
    rules: { completeness: 'Completeness: filed out of expected.', heat_map: 'Each cell.', qc: 'QC status.', timeliness: 'Working days.', expiring: 'Expiry.' },
    source: { mode: 'mock', as_of: '2026-11-09T00:00:00Z', sandbox_only: false, snapshot_days: 0 },
    ...overrides,
  }
}

describe('eTMF report', () => {
  it('colours completeness by how much is filed', () => {
    expect(completenessTone(null)).toBe('neutral')
    expect(completenessTone(100)).toBe('good')
    expect(completenessTone(80)).toBe('info')
    expect(completenessTone(50)).toBe('warn')
    expect(completenessTone(10)).toBe('bad')
  })

  it('shows completeness, missing by site, the section heat map, QC, timeliness and expiring documents', async () => {
    mockApi({ '/me': adminUser, '/reports/etmf': report() })
    renderRoute('/reports?tab=etmf')

    expect(await screen.findByTestId('tile-completeness')).toHaveTextContent('74.8%')
    expect(screen.getByRole('img', { name: 'eTMF completeness: 86 of 115 (74.8%)' })).toBeInTheDocument()
    expect(screen.getByText('Document metadata only: Avi.Intelligence never downloads eTMF files.')).toBeInTheDocument()
    expect(screen.getAllByTestId('study-completeness-row')[1]).toHaveTextContent('13 of 32 (40.6%)')
    expect(screen.getByTestId('site-missing-row')).toHaveTextContent('9 missing · 4 of 13 (30.8%)')

    const heat = screen.getByTestId('heat-row')
    expect(within(heat).getByTitle('301 · Demo Heart Institute, 01. General Site Documents: 0 of 2 (0%)')).toHaveTextContent('0/2')
    expect(within(heat).getByTitle('301 · Demo Heart Institute, 02. Site Personnel: none expected')).toHaveTextContent('—')

    expect(screen.getAllByTestId('qc-row')[0]).toHaveTextContent('Approved36')
    expect(screen.getByText('46 of 76 dated documents filed within the target.')).toBeInTheDocument()

    const expiring = screen.getAllByTestId('expiring-row')
    expect(within(expiring[0]!).getByText('Expired 12d ago')).toBeInTheDocument()
    expect(within(expiring[1]!).getByText('In 18 days')).toBeInTheDocument()
  })

  it('filters by study, in the URL and the Excel link', async () => {
    const fetchMock = mockApi({ '/me': viewerUser, '/reports/etmf': report() })
    const { router } = renderRoute('/reports?tab=etmf')
    await screen.findByTestId('tile-missing')
    await userEvent.click(screen.getByRole('combobox', { name: 'Filter by study' }))
    await userEvent.click(await screen.findByTitle('DEMO-ONC-301 · Oncology study'))
    expect(router.state.location.search).toBe('?tab=etmf&study=11111111-1111-1111-1111-111111111111')
    expect(fetchMock.mock.calls.some(([u]) => String(u).includes('/api/v1/reports/etmf?study_id=11111111'))).toBe(true)
    expect(screen.getByRole('link', { name: /Excel/ })).toHaveAttribute(
      'href',
      '/api/v1/reports/etmf/export.xlsx?study_id=11111111-1111-1111-1111-111111111111',
    )
  })

  it('explains when SimpleTrials has sent no eTMF documents', async () => {
    mockApi({
      '/me': adminUser,
      '/reports/etmf': report({
        has_documents: false,
        source: { mode: 'api', as_of: '2026-11-09T00:00:00Z', sandbox_only: true, snapshot_days: 0 },
      }),
    })
    renderRoute('/reports?tab=etmf')
    expect(await screen.findByText('No eTMF documents from SimpleTrials yet')).toBeInTheDocument()
    expect(screen.getByText('SimpleTrials sandbox study')).toBeInTheDocument()
  })
})
