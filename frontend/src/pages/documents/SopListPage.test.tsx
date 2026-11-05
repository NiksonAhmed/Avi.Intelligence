import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { adminUser, makeSop, makeSopList, mockApi, renderRoute } from '../../test/utils'
import { isReviewDue } from '../../lib/sops'

const docs = [
  makeSop(),
  makeSop({
    id: 'demo-sop-021',
    sop_number: 'SOP-021',
    title: 'Data Query Management',
    status: 'Draft',
    department: 'Data Management',
  }),
]

describe('SOP list page', () => {
  it('lists SOPs with status labels and flags demo data', async () => {
    mockApi({ '/me': adminUser, '/sops': makeSopList(docs) })
    renderRoute('/documents/sops')

    expect(await screen.findByRole('link', { name: 'Site Activation' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Data Query Management' })).toBeInTheDocument()
    expect(screen.getByText('Demo data: SharePoint is not connected')).toBeInTheDocument()

    const table = screen.getByRole('table')
    expect(within(table).getByText('Effective')).toBeInTheDocument()
    expect(within(table).getByText('Draft')).toBeInTheDocument()
  })

  it('shows SharePoint provenance and a refresh button for live data', async () => {
    mockApi({ '/me': adminUser, '/sops': makeSopList(docs, 'live') })
    renderRoute('/documents/sops')
    expect(await screen.findByText(/Source record · SharePoint/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Refresh from SharePoint/ })).toBeInTheDocument()
    expect(screen.queryByText(/Demo data/)).not.toBeInTheDocument()
  })

  it('sends the search term to the API and keeps it in the URL', async () => {
    const fetchMock = mockApi({
      '/me': adminUser,
      '/sops': (url: URL) =>
        makeSopList(url.searchParams.get('q') ? docs.slice(0, 1) : docs),
    })
    const { router } = renderRoute('/documents/sops')
    await screen.findByRole('link', { name: 'Data Query Management' })

    await userEvent.type(screen.getByRole('searchbox', { name: 'Search SOPs' }), 'activation{Enter}')

    await waitFor(() => expect(router.state.location.search).toBe('?q=activation'))
    await waitFor(() =>
      expect(screen.queryByRole('link', { name: 'Data Query Management' })).not.toBeInTheDocument(),
    )
    expect(fetchMock.mock.calls.some(([u]) => String(u).includes('/api/v1/sops?q=activation'))).toBe(true)
  })

  it('explains an empty result', async () => {
    mockApi({ '/me': adminUser, '/sops': { ...makeSopList([]), total_unfiltered: 4 } })
    renderRoute('/documents/sops?status=Retired')
    expect(await screen.findByText('No SOPs match these filters.')).toBeInTheDocument()
  })

  it('shows an error with retry when the API fails', async () => {
    mockApi({ '/me': adminUser })
    renderRoute('/documents/sops')
    expect(await screen.findByText('Could not load SOPs')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })
})

describe('isReviewDue', () => {
  const now = new Date('2026-01-01T00:00:00Z').getTime()
  it('flags effective SOPs due within 30 days', () => {
    expect(isReviewDue(makeSop({ review_date: '2026-01-15T00:00:00Z' }), now)).toBe(true)
    expect(isReviewDue(makeSop({ review_date: '2026-06-01T00:00:00Z' }), now)).toBe(false)
    expect(isReviewDue(makeSop({ review_date: '2026-01-15T00:00:00Z', status: 'Draft' }), now)).toBe(false)
  })
})
