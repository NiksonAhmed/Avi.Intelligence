import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import {
  adminUser,
  makeMilestone,
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

  it('shows Sync now to every role with study.sync, and hides it without', async () => {
    mockApi({ '/me': viewerUser, '/studies': makeStudyList([study]) })
    const { unmount } = renderRoute('/portfolio')
    await screen.findByRole('link', { name: 'DEMO-ONC-301' })
    expect(screen.queryByRole('button', { name: /Sync now/ })).not.toBeInTheDocument()
    unmount()
    const viewer = { ...viewerUser, permissions: [...viewerUser.permissions, 'study.sync'] }
    mockApi({ '/me': viewer, '/studies': makeStudyList([study]) })
    renderRoute('/portfolio')
    expect(await screen.findByRole('button', { name: /Sync now/ })).toBeInTheDocument()
  })
})

describe('Study Command Centre', () => {
  const routes = (me = adminUser, tasks = [makeTask()]) => ({
    '/me': me,
    [`/studies/${study.id}`]: makeStudyDetail(study),
    '/studies': makeStudyList([study]),
    '/tasks': {
      tasks: tasks.map((t) => ({ ...t, can_edit: me === adminUser })),
      can_manage: me === adminUser,
      can_create: me === adminUser ? ['study', 'sop', 'vendor', 'system', 'general'] : [],
      statuses: [],
    },
    '/risks': { simpletrials_issues: [] },
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

  it('shows SimpleTrials plan details and labels the sandbox study', async () => {
    const sandbox = makeStudy({ sandbox: true })
    const detail = makeStudyDetail(sandbox)
    detail.milestones = [
      makeMilestone({
        id: 'p4',
        kind: 'phase',
        is_key: false,
        name: '04. Site Startup Activities',
        planned_date: '2026-08-24',
        baseline_date: '2026-08-24',
        state: 'overdue',
        schedule: 'on_plan',
        variance_days: 0,
      }),
      makeMilestone({
        id: 'fpi',
        parent_external_id: 'p4',
        name: '04.05 First Patient In',
        phase: '04. Site Startup Activities',
        planned_date: '2026-06-11',
        baseline_date: '2026-06-09',
        percent_complete: 100,
        variance_days: 2,
        state: 'completed',
        schedule: 'slipped',
      }),
      makeMilestone({
        id: 'contract',
        parent_external_id: 'p4',
        kind: 'task',
        is_key: false,
        name: '04.03 Contract Negotiation',
        planned_date: '2026-07-01',
        baseline_date: '2026-05-01',
        variance_days: 61,
        state: 'overdue',
        schedule: 'slipped_major',
      }),
    ]
    mockApi({ ...routes(), [`/studies/${sandbox.id}`]: detail })
    renderRoute(`/command-centre/${sandbox.id}`)
    expect(await screen.findByText('SimpleTrials sandbox study')).toBeInTheDocument()

    // Key milestones view (default): the key milestone with both end dates and both statuses.
    expect(screen.getByText('04.05 First Patient In')).toBeInTheDocument()
    expect(screen.getByLabelText('Key milestone')).toBeInTheDocument()
    // (Scrollable tables render a measuring copy of the header, hence getAll.)
    expect(screen.getAllByText('Current').length).toBeGreaterThan(0) // grouped under Start / End
    expect(screen.getByText('+2 days')).toBeInTheDocument()
    expect(screen.getByText('Completed')).toBeInTheDocument()
    expect(screen.queryByText('04.03 Contract Negotiation')).not.toBeInTheDocument()

    // Full plan: phases and tasks as in SimpleTrials.
    await userEvent.click(screen.getByText('Full plan'))
    expect(await screen.findByText('04.03 Contract Negotiation')).toBeInTheDocument()
    expect(screen.getByText('+61 days')).toBeInTheDocument()
    expect(screen.getByText('On plan')).toBeInTheDocument()
    expect(screen.getAllByText('04. Site Startup Activities').length).toBeGreaterThan(0)
    // Phase headings only group the plan: no Assign button on them, only on their entries.
    expect(screen.queryByRole('button', { name: 'Assign a task for 04. Site Startup Activities' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Assign a task for 04.03 Contract Negotiation' })).toBeInTheDocument()
  })

  it('shows tasks assigned for plan items, green when completed, and offers Assign to admins', async () => {
    const detail = makeStudyDetail(study)
    detail.milestones = [
      makeMilestone({ id: 'start', name: '01.01 Study Start', planned_date: '2026-02-19', state: 'overdue' }),
      makeMilestone({ id: 'fpi', name: '04.05 First Patient In', planned_date: '2026-06-11', state: 'overdue' }),
    ]
    const done = makeTask({
      reference: 'TSK-0009',
      title: '01.01 Study Start',
      plan_item: { external_id: 'start', name: '01.01 Study Start' },
      assignees: [{ person_id: 'demo-cra-1', name: 'Demo CRA One', status: 'Completed', completed_at: null }],
      due_date: '2026-03-01',
      status: 'Completed',
      overdue: false,
    })
    mockApi({ ...routes(adminUser, [done]), [`/studies/${study.id}`]: detail })
    renderRoute(`/command-centre/${study.id}`)

    const cell = await screen.findByTestId('plan-task-TSK-0009')
    expect(cell).toHaveTextContent('Demo CRA One')
    expect(cell).toHaveTextContent('Due 01 Mar 26')
    expect(cell).toHaveTextContent('Completed')
    expect(cell.style.background).toContain('rgb(230, 244, 236)') // green (#E6F4EC) once completed
    // No task yet for First Patient In: administrators can assign one from the plan.
    await userEvent.click(screen.getByRole('button', { name: 'Assign a task for 04.05 First Patient In' }))
    expect(await screen.findByText('For plan item: 04.05 First Patient In')).toBeInTheDocument()
  })

  it('does not offer Assign on the plan to non-administrators', async () => {
    const detail = makeStudyDetail(study)
    detail.milestones = [makeMilestone({ id: 'fpi', name: '04.05 First Patient In', state: 'overdue' })]
    mockApi({ ...routes(viewerUser, []), [`/studies/${study.id}`]: detail })
    renderRoute(`/command-centre/${study.id}`)
    expect(await screen.findByText('04.05 First Patient In')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Assign a task/ })).not.toBeInTheDocument()
  })

  it('lets an administrator create tasks', async () => {
    mockApi(routes())
    renderRoute(`/command-centre/${study.id}?tab=tasks`)
    expect(await screen.findByRole('button', { name: /New task/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Edit TSK-0001' })).toBeInTheDocument()
  })

  it('is read-only for other roles', async () => {
    mockApi(routes(viewerUser, [makeTask({
        can_update_status: false,
        my_status: null,
        assignees: [{ person_id: 'x', name: 'Someone Else', status: 'Not started', completed_at: null }],
      })]))
    renderRoute(`/command-centre/${study.id}?tab=tasks`)
    expect(await screen.findByText('Collect signed CVs for site 102')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /New task/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edit TSK-0001' })).not.toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: 'Status of TSK-0001' })).not.toBeInTheDocument()
    expect(screen.getByLabelText('Read-only')).toBeInTheDocument()
  })

  it('shows not found for an unknown study', async () => {
    mockApi({ '/me': adminUser, '/tasks': { tasks: [] }, '/risks': { simpletrials_issues: [] } })
    renderRoute('/command-centre/00000000-0000-0000-0000-000000000000')
    expect(await screen.findByText('Study not found')).toBeInTheDocument()
  })
})

describe('My Tasks', () => {
  it('lets the assignee change the status of their own task', async () => {
    const calls: { url: string; body: string }[] = []
    mockApi({
      '/me': viewerUser,
      '/tasks': { tasks: [makeTask({ can_edit: false })], can_manage: false, can_create: [], statuses: [] },
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

describe('Risks and Issues', () => {
  const issue = {
    id: 'a1',
    number: '1',
    study: { id: study.id, protocol_number: 'DEMO-ONC-301', title: 'Demo study' },
    site_number: '101',
    site_name: 'Demo Hospital North',
    category: 'Site',
    subcategory: 'Site Visit',
    priority: 'High',
    status: 'New',
    closed: false,
    description: 'Demo: chase missing ISF delegation log signatures',
    response: null,
    assignee: 'Demo CRA',
    opened_on: '2026-10-23',
    due_on: '2026-11-06',
    closed_on: null,
    days_overdue: 6,
  }

  it('shows SimpleTrials action items as read-only issues, with overdue days', async () => {
    mockApi({ '/me': viewerUser, '/risks': { simpletrials_issues: [issue] } })
    renderRoute('/risks')
    const table = await screen.findByTestId('simpletrials-issues')
    expect(table).toHaveTextContent('From SimpleTrials')
    expect(table).toHaveTextContent('Read-only')
    const row = await screen.findByTestId('simpletrials-issue-row')
    expect(row).toHaveTextContent('DEMO-ONC-301')
    expect(row).toHaveTextContent('101 · Demo Hospital North')
    expect(row).toHaveTextContent('Demo: chase missing ISF delegation log signatures')
    expect(row).toHaveTextContent('Demo CRA')
    expect(screen.getByTestId('simpletrials-issue-overdue')).toHaveTextContent('6 days overdue')
  })

  it('is read-only: no raising, everyone can sync, and links to the dashboard', async () => {
    const admin = { ...adminUser, permissions: [...adminUser.permissions, 'study.sync'] }
    mockApi({ '/me': admin, '/risks': { simpletrials_issues: [] }, '/studies': { studies: [] } })
    renderRoute('/risks')
    expect(await screen.findByText('Risks and issues are managed in SimpleTrials')).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: /Sync now/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Raise risk or issue/ })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Dashboard/ })).toHaveAttribute('href', '/reports?tab=risks')
    expect(await screen.findByText('No open SimpleTrials action items.')).toBeInTheDocument()
  })
})
