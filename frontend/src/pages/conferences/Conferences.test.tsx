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
    priority: 2,
    team: 'AB',
    attendees: ['AB'],
    tags: [],
    gov_support: null,
    registration: 'EBR to 8 Dec',
    register_by: '2026-12-08',
    booth: null,
    website: null,
    notes: 'Clinical operations',
    source_url: null,
    past: false,
    days_until: 80,
    register_soon: true,
    clashes: [],
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
      conf({
        id: 'c2', name: 'Demo Rare Disease Congress', city: 'Boston', lat: 42.36, lon: -71.06, starts_on: '2027-04-20', ends_on: '2027-04-21',
        priority: 1, team: 'CD, AB', attendees: ['CD', 'AB'], tags: ['BIO Partnering'], gov_support: 'AusBio Trade Mission', website: 'https://example.org',
        register_soon: false, days_until: 158,
        clashes: [{ id: 'c3', name: 'Demo Somewhere New', starts_on: '2027-04-21', ends_on: '2027-04-22', shared: ['CD'] }],
      }),
      conf({
        id: 'c3', name: 'Demo Somewhere New', city: 'Atlantis', lat: null, lon: null, starts_on: '2027-04-21', ends_on: '2027-04-22', priority: 3,
        team: 'CD', attendees: ['CD'], register_soon: false, days_until: 159,
        clashes: [{ id: 'c2', name: 'Demo Rare Disease Congress', starts_on: '2027-04-20', ends_on: '2027-04-21', shared: ['CD'] }],
      }),
    ],
    clash_groups: [{ starts_on: '2027-04-20', ends_on: '2027-04-22', names: ['Demo Rare Disease Congress', 'Demo Somewhere New'], shared: ['CD'] }],
    next_id: 'c1',
    not_on_map: 1,
    attendees: ['AB', 'CD'],
    tags: ['BIO Partnering'],
    rules: { source: 'Conferences as recorded by the BD team.' },
    source: { mode: 'demo', reason: 'The BD team’s SharePoint conference list is not connected yet.', fetched_at: null },
    ...overrides,
  }
}

describe('Conferences', () => {
  it('shows demo conferences on the map, the next one selected, with a clear demo notice', async () => {
    mockApi({ '/me': viewerUser, '/conferences': report() })
    renderRoute('/conferences')
    expect(await screen.findByText(/Demo conferences: the BD team's SharePoint schedules are not connected yet/)).toBeInTheDocument()
    expect(screen.getAllByTestId('conference-pin')).toHaveLength(2) // the unknown city is not on the map
    expect(screen.getByText('1 not on the map (city not known yet)')).toBeInTheDocument()
    const details = screen.getByTestId('conference-details')
    expect(within(details).getByText('Demo Clinical Operations Summit')).toBeInTheDocument()
    expect(within(details).getByText(/Registration closes/)).toBeInTheDocument()
    expect(within(details).queryByText('Cost')).not.toBeInTheDocument()
    expect(screen.getAllByTestId('conference-row')).toHaveLength(3)
    // Date clashes, found by the server: the same person booked twice.
    expect(within(screen.getByTestId('conference-clashes')).getByText('CD booked twice')).toBeInTheDocument()
    expect(screen.getAllByText('Clash: CD booked twice')).toHaveLength(2) // both conferences in the clash
  })

  it('a pin opens its details (priority, people, gov support, clash), and filters go in the URL and the Excel link', async () => {
    const fetchMock = mockApi({ '/me': viewerUser, '/conferences': report() })
    const { router } = renderRoute('/conferences')
    await userEvent.click(await screen.findByRole('button', { name: /Demo Rare Disease Congress.*Priority 1, date clash: CD booked twice/ }))
    const details = screen.getByTestId('conference-details')
    expect(within(details).getByText('Priority 1')).toBeInTheDocument()
    expect(within(details).getByText('CD, AB')).toBeInTheDocument()
    expect(within(details).getByText('AusBio Trade Mission')).toBeInTheDocument()
    expect(within(details).getByText('Date clash: CD booked twice')).toBeInTheDocument()
    expect(within(details).getByRole('link', { name: 'Conference website' })).toHaveAttribute('href', 'https://example.org')
    await userEvent.click(screen.getByRole('button', { name: 'Priority 1' }))
    expect(router.state.location.search).toContain('priority=1')
    await userEvent.click(screen.getByRole('button', { name: 'CD' }))
    expect(router.state.location.search).toContain('who=CD')
    await userEvent.click(screen.getByRole('button', { name: 'BIO Partnering' }))
    await waitFor(() => expect(fetchMock.mock.calls.some(([u]) => String(u).includes('priority=1') && String(u).includes('who=CD'))).toBe(true))
    expect(screen.getByRole('link', { name: /Excel/ })).toHaveAttribute(
      'href',
      '/api/v1/conferences/export.xlsx?year=2027&priority=1&who=CD&tag=BIO+Partnering',
    )
  })

  it('shows no costs or budget, and the SharePoint link for real items', async () => {
    const live = report({
      source: { mode: 'sharepoint', reason: null, fetched_at: '2026-11-13T09:00:00Z' },
      conferences: [conf({ source_url: 'https://example.sharepoint.com/item/1' })],
    })
    mockApi({ '/me': adminUser, '/conferences': live })
    renderRoute('/conferences')
    const details = await screen.findByTestId('conference-details')
    expect(within(details).queryByText('Cost')).not.toBeInTheDocument()
    expect(within(details).queryByText(/Budget/)).not.toBeInTheDocument()
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
