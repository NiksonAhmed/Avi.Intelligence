import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { Providers } from '../../Providers'
import type { SiteAssignments } from '../../api/types'
import { createQueryClient } from '../../lib/queryClient'
import { adminUser, mockApi } from '../../test/utils'
import { SiteAssignmentsCard } from './SiteAssignmentsCard'

const data: SiteAssignments = {
  people: [
    { id: 'demo-pm-1', name: 'Demo PM One', job_title: 'Project Manager' },
    { id: 'demo-cra-1', name: 'Demo CRA One', job_title: 'Clinical Research Associate' },
  ],
  sites: [
    { key: 's1:501', label: 'SANDBOX-01 · 1001 · Sandbox Clinic' },
    { key: 's1:502', label: 'SANDBOX-01 · 1002 · Sandbox Research Centre' },
  ],
  assignments: {},
}

describe('CRA site assignments', () => {
  it('assigns sites to a CRA and saves them', async () => {
    const me = { ...adminUser, permissions: [...adminUser.permissions, 'work.manage'] }
    const fetchMock = mockApi({
      '/me': me,
      '/site-assignments': data,
      '/site-assignments/demo-cra-1': { ...data, assignments: { 'demo-cra-1': ['s1:501'] } },
    })
    const client = createQueryClient()
    client.setDefaultOptions({ queries: { retry: false } })
    render(
      <Providers client={client}>
        <SiteAssignmentsCard />
      </Providers>,
    )
    const card = await screen.findByTestId('site-assignments')
    expect(card).toHaveTextContent('Demo CRA One · Clinical Research Associate') // the first CRA is chosen
    await userEvent.click(screen.getByRole('combobox', { name: 'Sites' }))
    await userEvent.click(await screen.findByTitle('SANDBOX-01 · 1001 · Sandbox Clinic'))
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([u, init]) => String(u).includes('/site-assignments/demo-cra-1') && init?.method === 'PUT' && String(init.body).includes('s1:501'),
        ),
      ).toBe(true),
    )
    expect(await screen.findByText('Sites saved')).toBeInTheDocument()
  })
})
