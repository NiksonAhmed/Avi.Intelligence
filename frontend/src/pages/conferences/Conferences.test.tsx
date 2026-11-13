import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { Conference, ConferencesReport } from '../../api/types'
import { adminUser, mockApi, renderRoute, viewerUser } from '../../test/utils'

function conf(overrides: Partial<Conference>): Conference {
  return {
    id: 'c1',
    name: 'Demo Clinical Operations Summit',
    city: 'Orlando',
    country: 'USA',
    lat: 28.54,
    lon: -81.38,
    starts_on: '2027-02-01',
    ends_on: '2027-02-03',
    role: 'Attending',
    team: '2 people · BD',
    booth: null,
    register_by: '2026-12-08',
    website: null,
    notes: 'Clinical operations',
    source_url: null,
    cost: null,
    currency: null,
    past: false,
    days_until: 80,
    register_soon: true,
    ...overrides,
  }
}

function report(overrides: Partial<ConferencesReport> = {}): ConferencesReport {
  return {
    year: 2027,
    years: [2026, 2027],
    tiles: [
      { key: 'total', label: 'Conferences in 2027', value: '2', note: '2 still to come', tone: 'info' },
      { key: 'next', label: 'Next conference', value: 'In 80 days', note: 'Demo Clinical Operations Summit, Orlando', tone: 'info' },
    ],
    conferences: [
      conf({}),
      conf({ id: 'c2', name: 'Demo Rare Disease Congress', city: 'Boston', lat: 42.36, lon: -71.06, starts_on: '2027-04-20', ends_on: '2027-04-21', role: 'Speaking', register_soon: false, days_until: 158 }),
      conf({ id: 'c3', name: 'Demo Somewhere New', city: 'Atlantis', lat: null, lon: null, starts_on: '2027-06-01', ends_on: '2027-06-01', register_soon: false, days_until: 200 }),
    ],
    next_id: 'c1',
    not_on_map: 1,
    can_see_cost: false,
    rules: { source: 'Conferences as recorded by the BD team.' },
    source: { mode: 'demo', reason: 'The BD team’s SharePoint conference list is not connected yet.', fetched_at: null },
    ...overrides,
  }
}

describe('Conferences', () => {
  it('shows demo conferences on the map, the next one selected, with a clear demo notice', async () => {
    mockApi({ '/me': viewerUser, '/conferences': report() })
    renderRoute('/conferences')
    expect(await screen.findByText(/Demo conferences: the BD team's SharePoint list is not connected yet/)).toBeInTheDocument()
    expect(screen.getAllByTestId('conference-pin')).toHaveLength(2) // the unknown city is not on the map
    expect(screen.getByText('1 not on the map (city not known yet)')).toBeInTheDocument()
    const details = screen.getByTestId('conference-details')
    expect(within(details).getByText('Demo Clinical Operations Summit')).toBeInTheDocument()
    expect(within(details).getByText(/Registration closes/)).toBeInTheDocument()
    expect(within(details).queryByText('Cost')).not.toBeInTheDocument()
    expect(screen.getAllByTestId('conference-row')).toHaveLength(3)
  })

  it('selects a conference from its pin, and filters by role in the URL and the Excel link', async () => {
    const fetchMock = mockApi({ '/me': viewerUser, '/conferences': report() })
    const { router } = renderRoute('/conferences')
    await userEvent.click(await screen.findByRole('button', { name: /Demo Rare Disease Congress/ }))
    expect(within(screen.getByTestId('conference-details')).getByText('Demo Rare Disease Congress')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Speaking' }))
    expect(router.state.location.search).toContain('role=Speaking')
    await waitFor(() => expect(fetchMock.mock.calls.some(([u]) => String(u).includes('role=Speaking'))).toBe(true))
    expect(screen.getByRole('link', { name: /Excel/ })).toHaveAttribute('href', '/api/v1/conferences/export.xlsx?year=2027&role=Speaking')
  })

  it('shows costs only to those allowed, and the SharePoint link for real items', async () => {
    const live = report({
      can_see_cost: true,
      source: { mode: 'sharepoint', reason: null, fetched_at: '2026-11-13T09:00:00Z' },
      conferences: [conf({ cost: 4200, currency: 'USD', source_url: 'https://example.sharepoint.com/item/1' })],
    })
    mockApi({ '/me': adminUser, '/conferences': live })
    renderRoute('/conferences')
    const details = await screen.findByTestId('conference-details')
    expect(within(details).getByText('4,200 USD')).toBeInTheDocument()
    expect(within(details).getByRole('link', { name: 'Open in SharePoint' })).toHaveAttribute('href', 'https://example.sharepoint.com/item/1')
    expect(screen.queryByText(/Demo conferences/)).not.toBeInTheDocument()
  })

  it('appears in the menu right after Overview when switched on', async () => {
    const me = { ...viewerUser, permissions: [...viewerUser.permissions, 'conference.view'] }
    mockApi({ '/me': me, '/conferences': report(), '/overview': { view: 'viewer', view_label: 'Viewer', views: [], purpose: '', sources: [], attention: { counts: [], items: [] }, sections: [] } })
    renderRoute('/')
    const links = await screen.findAllByRole('link', { name: /Conferences/ })
    expect(links[0]).toHaveAttribute('href', '/conferences')
  })
})
