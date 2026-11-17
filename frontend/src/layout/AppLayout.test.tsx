import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { adminUser, bdUser, mockApi, renderRoute, viewerUser } from '../test/utils'

describe('App shell', () => {
  it('shows the main navigation grouped, in the agreed order', async () => {
    mockApi({ '/me': adminUser })
    renderRoute('/')
    const nav = await screen.findByRole('navigation', { name: 'Main navigation' })
    const labels = () =>
      within(nav)
        .getAllByRole('link')
        .map((a) => a.textContent)
    await waitFor(() => expect(labels().length).toBeGreaterThan(1))
    expect(labels()).toEqual([
      'Overview',
      'My Tasks',
      'Ask Avi.Intelligence',
      'Reports and Insights',
      'Study Portfolio',
      'Study Command Centre',
      'Site validation',
      'Documents and Knowledge',
      'Administration',
      'Audit Trail',
    ])
    for (const heading of ['Studies', 'Sites', 'Knowledge', 'Admin']) expect(within(nav).getByText(heading)).toBeInTheDocument()
    expect(screen.getByText('Skip to main content')).toBeInTheDocument()
  })

  it('shows Business Development only what its role allows', async () => {
    mockApi({ '/me': bdUser })
    renderRoute('/')
    const nav = await screen.findByRole('navigation', { name: 'Main navigation' })
    await waitFor(() =>
      expect(within(nav).getAllByRole('link').map((a) => a.textContent)).toEqual([
        'Overview',
        'My Tasks',
        'Ask Avi.Intelligence',
        'Study Portfolio',
        'Site validation',
        'Documents and Knowledge',
      ]),
    )
    expect(within(nav).queryByText('Admin')).not.toBeInTheDocument()
  })

  it('shows the current user and an honest empty notification centre', async () => {
    mockApi({ '/me': adminUser })
    renderRoute('/')
    expect(await screen.findByText('Jane Smith')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Notifications' }))
    expect(await screen.findByText(/No notifications yet/)).toBeInTheDocument()
  })

  it('the top-bar box asks Avi.Intelligence', async () => {
    mockApi({ '/me': adminUser })
    const { router } = renderRoute('/')
    await userEvent.type(
      await screen.findByRole('searchbox', { name: 'Search or ask anything' }),
      'consent{Enter}',
    )
    await waitFor(() => expect(router.state.location.pathname).toBe('/ask'))
    expect(router.state.location.search).toBe('?q=consent')
  })

  it('blocks connector settings for non-admin roles', async () => {
    mockApi({ '/me': viewerUser })
    renderRoute('/admin/connectors')
    expect(await screen.findByText("You don't have access")).toBeInTheDocument()
  })
})
