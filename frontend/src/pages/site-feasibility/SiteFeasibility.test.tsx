import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { SiteFeasibilityDetail, SiteFeasibilityReport } from '../../api/types'
import { adminUser, mockApi, renderRoute } from '../../test/utils'

const SOURCE = { mode: 'demo' as const, reason: 'Not connected yet.', fetched_at: null }

function report(): SiteFeasibilityReport {
  return {
    headline: '12 sites surveyed: 7 recommended for therapeutics and 9 for diagnostics.',
    tiles: [
      { key: 'sites', label: 'Sites surveyed', value: '12', note: '11 accepting new trials', tone: 'info' },
      { key: 'surveys_due', label: 'Surveys due', value: '3', note: 'over 12 months old', tone: 'warn' },
    ],
    sites: [
      { id: 'demo-103', name: 'Demo Site 103', city: 'Melbourne', state: 'VIC', lat: -37.81, lon: 144.96, recommendation: 'both', short: 'Diag · Ther', accepting: 'Yes', survey_due: false, hrec_weeks: 6 },
      { id: 'demo-109', name: 'Demo Site 109', city: 'Hobart', state: 'TAS', lat: -42.88, lon: 147.33, recommendation: 'not_assessed', short: 'Not assessed', accepting: 'No', survey_due: true, hrec_weeks: 14 },
    ],
    rows: [],
    surveys_due: [{ site_id: 'demo-109', site: 'Demo Site 109', city: 'Hobart', last_survey: '2025-07-06', months: 16 }],
    fastest: [{ site_id: 'demo-103', site: 'Demo Site 103', city: 'Melbourne', hrec_weeks: 6, contract_weeks: 8, startup_weeks: 10 }],
    isotope_options: ['64Cu', '68Ga', '90Y', '177Lu', '225Ac'],
    indication_options: ['Breast cancer', 'Melanoma'],
    recommendation_options: [
      { value: 'both', label: 'Diagnostics and therapeutics' },
      { value: 'therapeutics', label: 'Therapeutics only' },
    ],
    rules: { source: 'Demo.', recommendation: 'R.', survey: 'S.', answered: 'A.', score: 'Sc.', weeks: 'W.' },
    source: SOURCE,
  }
}

function detail(): SiteFeasibilityDetail {
  return {
    id: 'demo-103', name: 'Demo Site 103', department: 'Nuclear medicine', city: 'Melbourne', state: 'VIC', sector: 'Public',
    last_survey: '2026-08-20', last_survey_study: 'DEMO-ONC-301', survey_type: 'Site feasibility survey', accepting: 'Yes',
    withdrawal: null, recommend_diagnostics: 'Yes', recommend_therapeutics: 'Yes',
    timelines: { startup_weeks: 10, siv_weeks: 12, fpi_weeks: null },
    experience: {
      imaging_trials: 'Yes', therapeutic_trials: 'Yes', isotopes: ['64Cu', '90Y'], patient_identification: 'MDT meetings',
      by_indication: [
        { indication: 'Breast cancer', experience: 'Yes', imaging: 3, therapeutic: 2 },
        { indication: 'Melanoma', experience: 'No', imaging: 0, therapeutic: 0 },
      ],
      active_imaging_trials: 2,
    },
    ip: { licensed: ['64Cu', '90Y'], trained: ['64Cu'], handled: [], treatment_days: 'Mon to Thu', fridges: 1, freezers_20: 1, freezers_80: 0 },
    equipment: { ECG: 'Yes', 'Biosafety cabinet': 'No', 'Gamma counter': null },
    admin: {
      audited: 'Yes', auditor: 'Sponsor', major_findings: 'No', sops: 'Yes', radiation_licence: 'Current', central_hrec: 'Yes',
      hrec_weeks: 6, additional_approvals: 'RGO', contract_during_hrec: 'Yes', contract_weeks: 8, artnet: 'Yes (90Y)',
      remote_monitoring: 'Yes', remote_records: 'EMR read-only',
    },
    performance: {
      projects: [{ protocol: 'DEMO-ONC-301', indication: 'Prostate cancer', expected_min: 8, expected_max: 12, actual: 12 }],
      scores: { 'Time to RGO approval': 3 },
      competing_trials: 'No',
      comments: null,
    },
    source_url: null,
    recommendation: 'both',
    recommendation_label: 'Diagnostics and therapeutics',
    survey_due: false,
    answered: 96,
    score: 39,
    score_max: 40,
    score_rows: [
      { criterion: 'Time to RGO approval', score: 3, max: 3 },
      { criterion: 'Recruitment success', score: 5, max: 5 },
    ],
    validation_site_id: 'demo-103',
  }
}

describe('Site feasibility', () => {
  it('shows the headline, the map and the lists, labelled as demo data', async () => {
    mockApi({ '/me': adminUser, '/site-feasibility': report() })
    renderRoute('/site-feasibility')
    expect(await screen.findByTestId('feasibility-headline')).toHaveTextContent('12 sites surveyed')
    expect(screen.getByText(/Demo sites: the site feasibility tracker is not connected yet/)).toBeInTheDocument()
    expect(screen.getAllByTestId('site-pin')).toHaveLength(2)
    expect(screen.getByRole('button', { name: /Demo Site 109, Hobart TAS: Not assessed. Accepting new trials: No. Survey due/ })).toBeInTheDocument()
    expect(screen.getByText('Not accepting trials')).toBeInTheDocument()
    expect(screen.getByText('HREC 6 wk')).toBeInTheDocument()
    expect(screen.getByText('10 wk start-up')).toBeInTheDocument()
    expect(screen.getByText('16 months ago')).toBeInTheDocument()
  })

  it('filters go into the address', async () => {
    mockApi({ '/me': adminUser, '/site-feasibility': report() })
    const { router } = renderRoute('/site-feasibility')
    await userEvent.click(await screen.findByRole('button', { name: 'Therapeutics only' }))
    expect(router.state.location.search).toBe('?recommendation=therapeutics')
    await userEvent.click(screen.getByRole('button', { name: '225Ac' }))
    expect(router.state.location.search).toBe('?recommendation=therapeutics&isotope=225Ac')
  })

  it('clicking a site opens its feasibility, with a link to its validation', async () => {
    mockApi({ '/me': adminUser, '/site-feasibility': report(), '/site-feasibility/sites/demo-103': detail() })
    renderRoute('/site-feasibility')
    await userEvent.click(await screen.findByRole('button', { name: /Demo Site 103, Melbourne VIC/ }))
    const panel = await screen.findByTestId('feasibility-panel')
    expect(within(panel).getByText('Diagnostics and therapeutics')).toBeInTheDocument()
    expect(within(panel).getByText('39 of 40')).toBeInTheDocument()
    expect(within(panel).getByRole('link', { name: /Open on Site validation/ })).toHaveAttribute('href', '/site-validation?site=demo-103')
    // Start-up tab: an unanswered question says so.
    expect(within(panel).getByText('10 weeks')).toBeInTheDocument()
    expect(within(panel).getAllByText('Not answered').length).toBeGreaterThan(0)
    await userEvent.click(within(panel).getByRole('tab', { name: 'IP' }))
    expect(within(panel).getByTitle('Licensed for 90Y: yes')).toHaveTextContent('✓')
    expect(within(panel).getByTitle('Staff trained 90Y: no')).toHaveTextContent('–')
    await userEvent.click(within(panel).getByRole('tab', { name: 'Performance' }))
    expect(within(panel).getByText('Overall site assessment: 39 of 40')).toBeInTheDocument()
    expect(within(panel).getByText('8 to 12')).toBeInTheDocument()
  })
})
