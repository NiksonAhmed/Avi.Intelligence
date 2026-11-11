import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { adminUser, makeSopList, mockApi, renderRoute, viewerUser } from '../test/utils'

describe('App shell', () => {
  it('shows the main navigation in the agreed order', async () => {
    mockApi({ '/me': adminUser })
    renderRoute('/')
    const nav = await screen.findByRole('navigation', { name: 'Main navigation' })
    const labels = within(nav)
      .getAllByRole('link')
      .map((a) => a.textContent)
    expect(labels).toEqual([
      'Overview',
      'Study Portfolio',
      'Study Command Centre',
      'My Tasks',
      'Risks and Issues',
      'Documents and Knowledge',
      'Reports and Insights',
      'Administration',
      'Audit Trail',
    ])
    expect(screen.getByText('Skip to main content')).toBeInTheDocument()
  })

  it('shows the current user and an honest empty notification centre', async () => {
    mockApi({ '/me': adminUser })
    renderRoute('/')
    expect(await screen.findByText('Jane Smith')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Notifications' }))
    expect(await screen.findByText(/No notifications yet/)).toBeInTheDocument()
  })

  it('global search navigates to the SOP list', async () => {
    mockApi({ '/me': adminUser, '/sops': makeSopList([]) })
    const { router } = renderRoute('/')
    await userEvent.type(
      await screen.findByRole('searchbox', { name: 'Global search' }),
      'consent{Enter}',
    )
    await waitFor(() => expect(router.state.location.pathname).toBe('/documents/sops'))
    expect(router.state.location.search).toBe('?q=consent')
  })

  it('blocks connector settings for non-admin roles', async () => {
    mockApi({ '/me': viewerUser })
    renderRoute('/admin/connectors')
    expect(await screen.findByText("You don't have access")).toBeInTheDocument()
  })
})
