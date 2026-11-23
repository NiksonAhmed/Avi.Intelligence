import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import {
  adminUser,
  makeSop,
  makeSopDetail,
  makeSopList,
  makeTask,
  mockApi,
  qaUser,
  renderRoute,
} from '../../test/utils'
import type { Me } from '../../api/types'
import { assigneeSummary } from '../../lib/tasks'

const craUser: Me = {
  ...adminUser,
  id: 'cra9',
  role: 'cra',
  role_label: 'Clinical Research Associate',
  permissions: ['sop.read', 'sop.download', 'study.read', 'task.create_own'],
}

const people = [{ id: 'demo-cra-1', name: 'Demo CRA One', email: 'x', job_title: 'CRA', demo: true }]
const sop = makeSop()
const form = makeSop({
  id: 'demo-sop-011-a',
  sop_number: 'SOP-011-A',
  title: 'Site Initiation Visit Report Template',
  kind: 'form',
  parent_sop_number: 'SOP-011',
})
const draft = makeSop({ id: 'demo-sop-050', sop_number: 'SOP-050', title: 'Risk-Based QM', status: 'Draft' })

const sopTask = makeTask({
  id: '33333333-3333-3333-3333-333333333333',
  reference: 'TSK-0002',
  category: 'sop',
  category_label: 'Procedures and SOPs',
  study: null,
  title: 'Periodic review of SOP-011',
  documents: [{ sop_id: sop.id, kind: 'sop', sop_number: 'SOP-011', title: sop.title, version: '3.0' }],
})

function taskList(tasks = [makeTask(), sopTask], can_create: string[] = ['sop']) {
  return { tasks, can_manage: false, can_create, can_assign: can_create, categories: [], statuses: [] }
}

describe('Task categories', () => {
  it('QA creates a Procedures and SOPs task from approved SOPs only', async () => {
    const posted: unknown[] = []
    mockApi({
      '/me': qaUser,
      '/tasks': (_url: URL, init?: RequestInit) => {
        if (init?.method === 'POST') {
          posted.push(JSON.parse(String(init.body)))
          return sopTask
        }
        return taskList([])
      },
      '/sops': makeSopList([sop, form, draft]),
      '/people': people,
      '/studies': { studies: [] },
    })
    renderRoute('/tasks')

    await userEvent.click(await screen.findByRole('button', { name: /New task/ }))
    const dialog = await screen.findByRole('dialog')
    // QA's first category to assign is Procedures and SOPs.
    expect(within(dialog).getByText('Procedures and SOPs')).toBeInTheDocument()
    expect(within(dialog).queryByLabelText('Study')).not.toBeInTheDocument()

    await userEvent.click(within(dialog).getByRole('combobox', { name: 'SOPs and forms' }))
    expect(await screen.findByTitle('SOP-011 v3.0 · Site Activation')).toBeInTheDocument()
    expect(screen.queryByTitle(/SOP-050/)).not.toBeInTheDocument() // drafts never offered
    await userEvent.click(screen.getByTitle('SOP-011 v3.0 · Site Activation'))
    await userEvent.click(screen.getByTitle(/SOP-011-A/))

    await userEvent.type(within(dialog).getByLabelText('Task'), 'Periodic review of SOP-011')
    await userEvent.type(within(dialog).getByLabelText('What to review (optional)'), 'Check section 6')
    await userEvent.click(within(dialog).getByRole('combobox', { name: 'Assign to' }))
    await userEvent.click(await screen.findByTitle('Demo CRA One (CRA)'))
    await userEvent.click(screen.getByRole('button', { name: 'Create task' }))

    await waitFor(() => expect(posted).toHaveLength(1))
    expect(posted[0]).toMatchObject({
      category: 'sop',
      document_ids: ['demo-sop-011', 'demo-sop-011-a'],
      title: 'Periodic review of SOP-011',
      description: 'Check section 6',
      assignee_ids: ['demo-cra-1'],
    })
    expect(posted[0]).not.toHaveProperty('study_id')
  })

  it('admin chooses a vendor category and types its name', async () => {
    const posted: unknown[] = []
    mockApi({
      '/me': adminUser,
      '/tasks': (_url: URL, init?: RequestInit) => {
        if (init?.method === 'POST') {
          posted.push(JSON.parse(String(init.body)))
          return makeTask()
        }
        return taskList([], ['study', 'sop', 'vendor', 'system', 'general'])
      },
      '/people': people,
      '/studies': { studies: [] },
    })
    renderRoute('/tasks')
    await userEvent.click(await screen.findByRole('button', { name: /New task/ }))
    const dialog = await screen.findByRole('dialog')
    await userEvent.click(within(dialog).getByRole('combobox', { name: 'Category' }))
    await userEvent.click(await screen.findByTitle('Vendor'))
    await userEvent.type(await within(dialog).findByLabelText('Vendor name'), 'Acme Central Lab')
    await userEvent.type(within(dialog).getByLabelText('Task'), 'Annual requalification')
    await userEvent.click(within(dialog).getByRole('combobox', { name: 'Assign to' }))
    await userEvent.click(await screen.findByTitle('Demo CRA One (CRA)'))
    await userEvent.click(screen.getByRole('button', { name: 'Create task' }))
    await waitFor(() => expect(posted).toHaveLength(1))
    expect(posted[0]).toMatchObject({ category: 'vendor', subject_name: 'Acme Central Lab' })
  })

  it('My Tasks shows what each task is about and filters by category', async () => {
    const fetchMock = mockApi({ '/me': qaUser, '/tasks': taskList() })
    renderRoute('/tasks?scope=all')
    const link = await screen.findByRole('link', { name: 'SOP-011 v3.0' })
    expect(link).toHaveAttribute('href', '/documents/sops/demo-sop-011')
    expect(screen.getByRole('link', { name: 'DEMO-ONC-301' })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('combobox', { name: 'Filter by category' }))
    await userEvent.click(await screen.findByTitle('Procedures and SOPs'))
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([u]) => String(u).includes('category=sop'))).toBe(true),
    )
  })

  it('SOP page lists its tasks and offers New task to QA', async () => {
    const fetchMock = mockApi({
      '/me': qaUser,
      '/sops/demo-sop-011': makeSopDetail(sop),
      '/tasks': taskList([{ ...sopTask, can_edit: true }]),
    })
    renderRoute('/documents/sops/demo-sop-011')
    expect(await screen.findByText('Tasks for this SOP')).toBeInTheDocument()
    expect(await screen.findByText('Periodic review of SOP-011')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /New task/ })).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([u]) => String(u).includes('sop_id=demo-sop-011'))).toBe(true)
  })

  it('a CRA adds a task for themselves only, never an SOP task', async () => {
    const posted: unknown[] = []
    mockApi({
      '/me': craUser,
      '/tasks': (_url: URL, init?: RequestInit) => {
        if (init?.method === 'POST') {
          posted.push(JSON.parse(String(init.body)))
          return makeTask()
        }
        return { ...taskList([], ['study', 'vendor', 'system', 'general']), can_assign: [] }
      },
      '/people': [...people, { id: 'cra9', name: 'Casey CRA', email: 'x', job_title: 'CRA', demo: true }],
      '/studies': { studies: [] },
    })
    renderRoute('/tasks')
    await userEvent.click(await screen.findByRole('button', { name: /New task/ }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText(/for yourself only/)).toBeInTheDocument()
    await userEvent.click(within(dialog).getByRole('combobox', { name: 'Category' }))
    expect(screen.queryByTitle('Procedures and SOPs')).not.toBeInTheDocument()
    await userEvent.click(await screen.findByTitle('General'))
    await userEvent.type(within(dialog).getByLabelText('Task'), 'Prepare SIV slides')
    await userEvent.click(screen.getByRole('button', { name: 'Create task' }))
    await waitFor(() => expect(posted).toHaveLength(1))
    expect(posted[0]).toMatchObject({ category: 'general', assignee_ids: ['cra9'] })
  })

  it('shows several people, their progress and my own part', async () => {
    const shared = makeTask({
      title: 'Complete GCP refresher',
      assignees: [
        { person_id: 'u1', name: 'Jane Smith', status: 'Completed', completed_at: null },
        { person_id: 'p2', name: 'Demo CRA Two', status: 'Not started', completed_at: null },
        { person_id: 'p3', name: 'Demo Data Manager', status: 'In progress', completed_at: null },
      ],
      progress: { completed: 1, total: 3 },
      status: 'In progress',
      my_status: 'Completed',
      can_edit: false,
    })
    mockApi({ '/me': adminUser, '/tasks': taskList([shared]) })
    renderRoute('/tasks')
    expect(await screen.findByText(/Your part · 1 of 3 completed/)).toBeInTheDocument()
    expect(assigneeSummary(shared.assignees.map((a) => a.name))).toBe('Jane Smith +2')
    expect(assigneeSummary(['A', 'B'])).toBe('A and B')
    expect(screen.getByRole('combobox', { name: 'Status of TSK-0001' })).toBeInTheDocument()
  })
})
