import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import {
  adminUser,
  makeStudy,
  makeStudyDetail,
  makeStudyList,
  makeTask,
  mockApi,
  renderRoute,
  viewerUser,
} from '../../test/utils'
import { enrolmentText, taskBucket } from '../../lib/studies'

const study = makeStudy()
const noTarget = makeStudy({
  id: '33333333-3333-3333-3333-333333333333',
  protocol_number: 'DEMO-RES-202',
  title: 'Asthma demo study',
  enrolled: 9,
  enrolment_target: null,
  enrolment_percent: null,
  overdue_milestones: 0,
  next_milestone: null,
})

describe('Study Portfolio', () => {
  it('lists studies, flags demo data and never guesses enrolment', async () => {
    mockApi({ '/me': adminUser, '/studies': makeStudyList([study, noTarget]) })
    renderRoute('/portfolio')

    expect(await screen.findByRole('link', { name: 'DEMO-ONC-301' })).toBeInTheDocument()
    expect(screen.getByText('Demo data: SimpleTrials is not connected')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'DEMO-RES-202' })).toBeInTheDocument()
    // Summary counts are sums of recorded values only.
    expect(screen.getByText('Overdue milestones')).toBeInTheDocument()
  })

  it('shows Sync now only to users who manage connectors', async () => {
    mockApi({ '/me': viewerUser, '/studies': makeStudyList([study]) })
    renderRoute('/portfolio')
    await screen.findByRole('link', { name: 'DEMO-ONC-301' })
    expect(screen.queryByRole('button', { name: /Sync now/ })).not.toBeInTheDocument()
  })
})

describe('Study Command Centre', () => {
  const routes = (me = adminUser, tasks = [makeTask()]) => ({
    '/me': me,
    [`/studies/${study.id}`]: makeStudyDetail(study),
    '/studies': makeStudyList([study]),
    '/tasks': { tasks, can_manage: me === adminUser, statuses: [] },
    '/risks': { risks: [], can_manage: me === adminUser, statuses: [] },
    '/people': [],
  })

  it('shows key information and milestones with explained states', async () => {
    mockApi(routes())
    renderRoute(`/command-centre/${study.id}`)
    expect(await screen.findByRole('heading', { name: /DEMO-ONC-301 · Phase III oncology demo study/ })).toBeInTheDocument()
    expect(screen.getByText('Key information')).toBeInTheDocument()
    expect(screen.getByText('First patient in')).toBeInTheDocument()
    expect(screen.getByText('Overdue')).toBeInTheDocument()
  })

  it('shows site enrolment against target, and says when no target is recorded', async () => {
    mockApi({ ...routes(), [`/studies/${noTarget.id}`]: makeStudyDetail(noTarget) })
    const { unmount } = renderRoute(`/command-centre/${study.id}?tab=sites`)
    expect(await screen.findByText('31 of 40 (77.5%)')).toBeInTheDocument()
    expect(screen.getByText('53 of 120 (44.2%)')).toBeInTheDocument()
    unmount()
    renderRoute(`/command-centre/${noTarget.id}`)
    expect(await screen.findByText('9 enrolled · no target recorded')).toBeInTheDocument()
  })

  it('lets an administrator create tasks', async () => {
    mockApi(routes())
    renderRoute(`/command-centre/${study.id}?tab=tasks`)
    expect(await screen.findByRole('button', { name: /New task/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Edit TSK-0001' })).toBeInTheDocument()
  })

  it('is read-only for other roles', async () => {
    mockApi(routes(viewerUser, [makeTask({ can_update_status: false, assignee_name: 'Someone Else' })]))
    renderRoute(`/command-centre/${study.id}?tab=tasks`)
    expect(await screen.findByText('Collect signed CVs for site 102')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /New task/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edit TSK-0001' })).not.toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: 'Status of TSK-0001' })).not.toBeInTheDocument()
    expect(screen.getByLabelText('Read-only')).toBeInTheDocument()
  })

  it('shows not found for an unknown study', async () => {
    mockApi({ '/me': adminUser, '/tasks': { tasks: [] }, '/risks': { risks: [] } })
    renderRoute('/command-centre/00000000-0000-0000-0000-000000000000')
    expect(await screen.findByText('Study not found')).toBeInTheDocument()
  })
})

describe('My Tasks', () => {
  it('lets the assignee change the status of their own task', async () => {
    const calls: { url: string; body: string }[] = []
    mockApi({
      '/me': viewerUser,
      '/tasks': { tasks: [makeTask()], can_manage: false, statuses: [] },
      [`/tasks/${makeTask().id}/status`]: (url: URL, init?: RequestInit) => {
        calls.push({ url: url.pathname, body: String(init?.body) })
        return makeTask({ status: 'In progress' })
      },
    })
    renderRoute('/tasks')

    const select = await screen.findByRole('combobox', { name: 'Status of TSK-0001' })
    expect(screen.queryByRole('button', { name: /New task/ })).not.toBeInTheDocument()
    await userEvent.click(select)
    expect(screen.queryByTitle('Cancelled')).not.toBeInTheDocument() // only admins cancel
    await userEvent.click(await screen.findByTitle('In progress'))
    await waitFor(() => expect(calls).toHaveLength(1))
    expect(JSON.parse(calls[0]!.body)).toEqual({ status: 'In progress' })
  })

  it('requests only my tasks by default and explains an empty list', async () => {
    const fetchMock = mockApi({ '/me': viewerUser, '/tasks': { tasks: [], can_manage: false, statuses: [] } })
    renderRoute('/tasks')
    expect(await screen.findByText(/Nothing assigned to you/)).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([u]) => String(u).includes('/api/v1/tasks?assignee=me'))).toBe(true)
  })
})

describe('study helpers', () => {
  it('describes enrolment without estimating', () => {
    expect(enrolmentText(null, 100, null)).toBe('Not reported')
    expect(enrolmentText(5, null, null)).toBe('5 enrolled · no target recorded')
    expect(enrolmentText(5, 10, 50)).toBe('5 of 10 (50%)')
  })

  it('buckets tasks by due date', () => {
    const today = new Date(2026, 10, 5)
    expect(taskBucket('2026-11-01', true, today)).toBe('overdue')
    expect(taskBucket('2026-11-10', false, today)).toBe('week')
    expect(taskBucket('2026-12-01', false, today)).toBe('later')
    expect(taskBucket(null, false, today)).toBe('later')
  })
})
