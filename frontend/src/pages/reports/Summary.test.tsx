import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { ReportSummary } from '../../api/types'
import { adminUser, mockApi, renderRoute } from '../../test/utils'

const STUDY = '11111111-1111-1111-1111-111111111111'

function summary(): ReportSummary {
  return {
    cards: [
      { key: 'enrolment', label: 'Patients enrolled', value: '142', foot: 'Target 200', tone: 'info', change: '+27 since 17 Oct', change_tone: 'good' },
      { key: 'milestones', label: 'Key milestones overdue', value: '3', foot: '0 slipped over 30 days', tone: 'bad', change: null, change_tone: 'neutral' },
      { key: 'issues', label: 'Open risks and issues', value: '7', foot: '2 overdue', tone: 'warn', change: null, change_tone: 'neutral' },
      { key: 'deviations', label: 'Open deviations', value: '5', foot: '1 major or critical', tone: 'bad', change: null, change_tone: 'neutral' },
    ],
    studies: [
      { id: STUDY, protocol_number: 'DEMO-ONC-301', what: 'Oncology · Phase III · 5 sites', status: 'off_track', reason: 'Last site activated 12 days late', enrolled: 142, target: 200, percent: 71 },
    ],
    enrolment: [{ month: '2026-11', total: 142, new: null }],
    enrolment_target: 200,
    sparks: [{ key: 'issues', label: 'Open issues', value: '7', points: [] }],
    sites: [
      { key: 'activated', label: 'Activated', count: 5 },
      { key: 'pending', label: 'Not yet', count: 1 },
      { key: 'late', label: 'Late', count: 1 },
    ],
    rings: [{ key: 'etmf', label: 'eTMF complete', percent: 75, left: '87 filed', right: '29 missing' }],
    details: {
      issues: { title: 'Open risks and issues', summary: '7 open in SimpleTrials, 2 overdue.', report: 'risks', study_id: null, rows: [{ label: 'Chase delegation log · Site 104', chip: '12 days overdue', tone: 'bad' }] },
      [`study:${STUDY}`]: { title: 'DEMO-ONC-301 · Off track', summary: 'Last site activated 12 days late.', report: 'study', study_id: STUDY, rows: [] },
      etmf: { title: 'eTMF complete', summary: '87 of 116 filed.', report: 'etmf', study_id: null, rows: [] },
    },
    history_since: '2026-11-16',
    rules: { status: 'Off track: a key milestone is overdue.', source: 'From the full reports.', enrolment: 'Monthly.' },
    source: { mode: 'api', as_of: '2026-11-16T09:40:00Z', sandbox_only: false, snapshot_days: 1 },
  }
}

describe('Reports summary', () => {
  it('opens on the summary, with the tabs in the agreed order', async () => {
    mockApi({ '/me': adminUser, '/reports/summary': summary() })
    renderRoute('/reports')
    expect(await screen.findByTestId('summary-card-enrolment')).toHaveTextContent('142')
    expect(screen.getAllByRole('tab').map((t) => t.textContent)).toEqual([
      'Summary',
      'Study delivery',
      'Risks and issues',
      'Protocol deviations',
      'eTMF',
      'Quality (SOPs)',
      'Work management',
    ])
    expect(screen.getByText('+27 since 17 Oct')).toBeInTheDocument()
    expect(screen.getByTestId('summary-study')).toHaveTextContent('Off track')
    expect(screen.getByTestId('summary-ring-etmf')).toHaveTextContent('75%')
    expect(screen.getByText(/Trend builds up from/)).toBeInTheDocument()
  })

  it('shows the detail behind a card, then opens the full report', async () => {
    mockApi({ '/me': adminUser, '/reports/summary': summary() })
    const { router } = renderRoute('/reports')
    await userEvent.click(await screen.findByRole('button', { name: /Open risks and issues: 7/ }))
    const panel = await screen.findByTestId('summary-detail')
    expect(within(panel).getByText('Chase delegation log · Site 104')).toBeInTheDocument()
    await userEvent.click(within(panel).getByRole('button', { name: 'Open the full report' }))
    expect(router.state.location.search).toBe('?tab=risks')
  })

  it('a study opens its own full report, filtered to that study', async () => {
    mockApi({ '/me': adminUser, '/reports/summary': summary() })
    const { router } = renderRoute('/reports')
    await userEvent.click(await screen.findByRole('button', { name: /DEMO-ONC-301: Off track/ }))
    await userEvent.click(within(await screen.findByTestId('summary-detail')).getByRole('button', { name: 'Open the full report' }))
    expect(router.state.location.search).toBe(`?tab=study&study=${STUDY}`)
  })
})
