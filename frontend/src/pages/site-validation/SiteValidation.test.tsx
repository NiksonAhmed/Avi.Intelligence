import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { SiteDetail, SiteValidationReport } from '../../api/types'
import { adminUser, mockApi, renderRoute } from '../../test/utils'

const SOURCE = { mode: 'demo' as const, reason: 'Not connected yet.', fetched_at: null }

function report(): SiteValidationReport {
  return {
    headline: '9 of 12 sites hold an in-date validation. Demo Site 103 · PET/CT 90Y is overdue.',
    tiles: [
      { key: 'validated', label: 'Sites validated', value: '9 of 12', note: 'At least one in-date validation', tone: 'info' },
      { key: 'overdue', label: 'Overdue', value: '1', note: 'Review date has passed', tone: 'bad' },
    ],
    sites: [
      { id: 'demo-103', name: 'Demo Site 103', city: 'Melbourne', state: 'VIC', lat: -37.81, lon: 144.96, status: 'overdue', equipment: ['PET', 'SPECT', 'DC', 'GC'], attention: true },
      { id: 'demo-111', name: 'Demo Site 111', city: 'Darwin', state: 'NT', lat: -12.46, lon: 130.84, status: 'none', equipment: ['SPECT', 'DC'], attention: false },
    ],
    reviews: [{ site_id: 'demo-103', site: 'Demo Site 103', city: 'Melbourne', equipment: 'PET/CT', isotope: '90Y', physicist: 'Physicist (demo C)', next_review: '2026-11-05', days: -12 }],
    scans: [{ site_id: 'demo-103', site: 'Demo Site 103', city: 'Melbourne', study: 'DEMO-ONC-301', equipment: 'PET/CT', isotope: '90Y', status: 'Scanned', on: '2026-11-10' }],
    rows: [],
    equipment_options: ['PET/CT', 'SPECT/CT', 'Dose calibrator', 'Gamma counter'],
    isotope_options: ['64Cu', '68Ga', '90Y', '177Lu', '225Ac'],
    rules: { source: 'Demo.', review: '12 months.', status: 'Rules.', map: 'Map.' },
    source: SOURCE,
  }
}

function detail(): SiteDetail {
  const isotopes = ['64Cu', '68Ga', '90Y', '177Lu', '225Ac']
  return {
    id: 'demo-103', name: 'Demo Site 103', department: 'Nuclear medicine', city: 'Melbourne', state: 'VIC', status: 'overdue',
    last_survey: '2026-08-12', artnet_accreditation: 'Yes (90Y, 225Ac)', physicist: 'Physicist (demo C)', radiopharmacy: true,
    licensed: ['64Cu', '90Y'],
    equipment: [{ kind: 'PET/CT', manufacturer: 'GE', model: 'PET/CT (demo model)', installed: '2020-03-01', last_calibration: '2026-10-08', maintenance: 'Quarterly', replacement: 'Planned next year' }],
    missing_equipment: ['SPECT/CT', 'Dose calibrator', 'Gamma counter'],
    isotopes,
    grid: isotopes.map((i) => ({
      equipment: 'PET/CT' as const, isotope: i, state: i === '90Y' ? ('overdue' as const) : ('none' as const), validated: i === '90Y',
      tip: i === '90Y' ? 'PET/CT · 90Y: Overdue' : `PET/CT · ${i}: not validated`,
    })),
    qa: { phantoms: ['NEMA IEC Body Phantom'], used_for_study_scans: 'Yes', records_access: 'Yes', monthly_submission: 'Yes', daily_qc_storage: 'Internal server', routines: { 'PET/CT': 'Daily QC' } },
    transfer: { pacs: 'Demo PACS', dicom_export: 'Yes', methods: ['sFTP'] },
    scans: [{ study: 'DEMO-ONC-301', equipment: 'PET/CT', isotope: '90Y', status: 'Scanned', on: '2026-11-10' }],
    rows: [],
    source_url: null,
    source: SOURCE,
  }
}

describe('Site validation', () => {
  it('shows the headline, the map and the lists, labelled as demo data', async () => {
    mockApi({ '/me': adminUser, '/site-validation': report() })
    renderRoute('/site-validation')
    expect(await screen.findByTestId('site-headline')).toHaveTextContent('9 of 12 sites')
    expect(screen.getByText(/Demo sites: the site validation tracker is not connected yet/)).toBeInTheDocument()
    expect(screen.getAllByTestId('site-pin')).toHaveLength(2)
    expect(screen.getByRole('button', { name: /Demo Site 103, Melbourne VIC: Overdue/ })).toBeInTheDocument()
    expect(screen.getByText('Overdue by 12 days')).toBeInTheDocument()
    expect(screen.getByText('Scanned')).toBeInTheDocument()
  })

  it('a filter goes into the address', async () => {
    mockApi({ '/me': adminUser, '/site-validation': report() })
    const { router } = renderRoute('/site-validation')
    await userEvent.click(await screen.findByRole('button', { name: '225Ac' }))
    expect(router.state.location.search).toBe('?isotope=225Ac')
  })

  it('clicking a site opens its capabilities', async () => {
    mockApi({ '/me': adminUser, '/site-validation': report(), '/site-validation/sites/demo-103': detail() })
    renderRoute('/site-validation')
    await userEvent.click(await screen.findByRole('button', { name: /Demo Site 103, Melbourne VIC/ }))
    const panel = await screen.findByTestId('site-panel')
    expect(within(panel).getByText('Physicist (demo C)')).toBeInTheDocument()
    expect(within(panel).getByRole('table', { name: 'Isotope validation' })).toBeInTheDocument()
    expect(within(panel).getByLabelText('PET/CT · 90Y: Overdue')).toHaveTextContent('✕')
    expect(within(panel).getByText('NEMA IEC Body Phantom')).toBeInTheDocument()
    expect(within(panel).getByText('Not on site: SPECT/CT, Dose calibrator, Gamma counter')).toBeInTheDocument()
    expect(within(panel).getByText('sFTP')).toBeInTheDocument()
  })
})
