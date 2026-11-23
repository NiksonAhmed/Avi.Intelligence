import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { OverviewData } from '../../api/types'
import { adminUser, mockApi, renderRoute, viewerUser } from '../../test/utils'

function overview(overrides: Partial<OverviewData> = {}): OverviewData {
  return {
    view: 'cra',
    view_label: 'Clinical Research Associate',
    views: [{ id: 'cra', label: 'Clinical Research Associate' }],
    purpose: 'Your sites: visits coming up, what to chase, and what to check at the next visit.',
    sources: [
      { name: 'SimpleTrials', as_of: '2026-11-13T09:02:00Z', ok: true },
      { name: 'SharePoint', as_of: '2026-11-13T08:55:00Z', ok: true },
    ],
    attention: {
      counts: [
        { label: 'Your overdue tasks', value: '1', note: null, tone: 'bad', link: '/tasks' },
        { label: 'Your tasks due in the next 7 days', value: '2', note: null, tone: 'warn', link: '/tasks' },
        { label: 'Site visits in the next 14 days', value: '1', note: null, tone: 'warn', link: '/command-centre' },
      ],
      items: [{ label: 'TSK-0014 · Chase ethics renewal', detail: 'Study · SANDBOX-01', chip: '5 days late', tone: 'bad', link: '/tasks' }],
    },
    sections: [
      {
        key: 'my_sites',
        title: 'Sites',
        source: 'from SimpleTrials',
        link: '/command-centre',
        link_label: 'Study Command Centre',
        kpis: [],
        rows: [
          { label: '1001 · Sandbox Clinic', detail: 'SANDBOX-01 · 3 enrolled · 3 overdue action items', chip: 'Next visit Tue 17 Nov', tone: 'bad', link: '/command-centre/s1?tab=sites' },
        ],
        notice: 'No sites are assigned to you yet, so all sites are shown. An administrator assigns sites in Administration.',
        empty: 'No sites.',
      },
      {
        key: 'risks',
        title: 'Risks and issues',
        source: 'from SimpleTrials',
        link: '/reports?tab=risks',
        link_label: 'Risks and issues report',
        kpis: [{ label: 'Open issues', value: '3', note: '3 recorded in all', tone: 'warn', link: '/reports?tab=risks' }],
        rows: [],
        notice: null,
        empty: 'No open risks or issues.',
      },
    ],
    ...overrides,
  }
}

describe('Overview', () => {
  it('shows what needs you, then your role’s sections, each linking to its detail', async () => {
    mockApi({ '/me': viewerUser, '/overview': overview() })
    renderRoute('/')
    expect(await screen.findByText('Needs your attention')).toBeInTheDocument()
    const counts = screen.getAllByTestId('overview-attention-count')
    expect(counts).toHaveLength(3)
    expect(counts[0]).toHaveTextContent('1Your overdue tasks')
    expect(counts[0]).toHaveAttribute('href', '/tasks')
    expect(screen.getByTestId('overview-task')).toHaveTextContent('5 days late')
    const sites = screen.getByTestId('overview-section-my_sites')
    expect(within(sites).getByText(/No sites are assigned to you yet/)).toBeInTheDocument()
    expect(within(sites).getByRole('link', { name: '1001 · Sandbox Clinic' })).toHaveAttribute('href', '/command-centre/s1?tab=sites')
    const risks = screen.getByTestId('overview-section-risks')
    expect(within(risks).getByRole('link', { name: /3Open issues/ })).toHaveAttribute('href', '/reports?tab=risks')
    expect(within(risks).getByText('No open risks or issues.')).toBeInTheDocument()
    expect(screen.getAllByTestId('overview-source')).toHaveLength(2)
    expect(screen.queryByRole('combobox', { name: 'View the Overview as' })).not.toBeInTheDocument()
  })

  it('lets an administrator view another role’s page', async () => {
    const views = [
      { id: 'admin', label: 'Administrator' },
      { id: 'cra', label: 'Clinical Research Associate' },
    ]
    const fetchMock = mockApi({ '/me': adminUser, '/overview': overview({ view: 'admin', view_label: 'Administrator', views }) })
    const { router } = renderRoute('/')
    await userEvent.click(await screen.findByRole('combobox', { name: 'View the Overview as' }))
    await userEvent.click(await screen.findByTitle('View as Clinical Research Associate'))
    expect(router.state.location.search).toBe('?view=cra')
    await waitFor(() => expect(fetchMock.mock.calls.some(([u]) => String(u).includes('/overview?view=cra'))).toBe(true))
  })

  it('syncs every source with Sync all', async () => {
    const me = { ...viewerUser, permissions: [...viewerUser.permissions, 'study.sync'] }
    const fetchMock = mockApi({ '/me': me, '/overview': overview(), '/sops/refresh': null, '/studies/sync': { last_sync: { ok: true } } })
    renderRoute('/')
    await userEvent.click(await screen.findByRole('button', { name: /Sync all/ }))
    expect(await screen.findByText('All sources synced')).toBeInTheDocument()
    const posted = fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST').map(([u]) => new URL(String(u), 'http://x').pathname)
    expect(posted).toEqual(expect.arrayContaining(['/api/v1/sops/refresh', '/api/v1/studies/sync']))
  })
})
