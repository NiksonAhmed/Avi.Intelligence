import { render } from '@testing-library/react'
import { createMemoryRouter } from 'react-router'
import { RouterProvider } from 'react-router/dom'
import { vi } from 'vitest'

import type {
  Me,
  Milestone,
  SopDetailResponse,
  SopDocument,
  SopListResponse,
  StudyDetailResponse,
  StudyListResponse,
  StudySource,
  StudySummary,
  Task,
} from '../api/types'
import { Providers } from '../Providers'
import { createQueryClient } from '../lib/queryClient'
import { routes } from '../router'

export const adminUser: Me = {
  id: 'u1',
  name: 'Jane Smith',
  email: 'jane@example.com',
  role: 'admin',
  role_label: 'Administrator',
  permissions: ['audit.read', 'connector.manage', 'sop.download', 'sop.read', 'study.read', 'work.manage'],
  auth_mode: 'development',
}

export const qaUser: Me = {
  ...adminUser,
  id: 'qa1',
  role: 'qa',
  role_label: 'Quality Assurance',
  permissions: [
    'audit.read',
    'sop.download',
    'sop.read',
    'study.read',
    'task.assign.sop',
    'task.assign.vendor',
    'task.assign.system',
    'task.assign.general',
    'task.create_own',
  ],
}

export const viewerUser: Me = {
  ...adminUser,
  role: 'viewer',
  role_label: 'Viewer',
  permissions: ['sop.read', 'study.read'],
}

export function makeSop(overrides: Partial<SopDocument> = {}): SopDocument {
  return {
    id: 'demo-sop-011',
    title: 'Site Activation',
    file_name: 'SOP-011 Site Activation v3.0.docx',
    sop_number: 'SOP-011',
    kind: 'sop',
    parent_sop_number: null,
    version: '3.0',
    status: 'Effective',
    status_source: 'column',
    effective_date: '2025-01-20T00:00:00Z',
    review_date: '2027-01-20T00:00:00Z',
    owner: 'Director, Clinical Operations',
    department: 'Clinical Operations',
    folder_path: 'SOPs/Clinical Operations',
    modified_at: '2025-01-20T00:00:00Z',
    modified_by: 'Demo data',
    web_url: null,
    size_bytes: 52000,
    mime_type: 'application/pdf',
    ...overrides,
  }
}

export function makeSopList(docs: SopDocument[], mode: 'live' | 'mock' = 'mock'): SopListResponse {
  return {
    documents: docs,
    total_unfiltered: docs.length,
    summary: {
      total: docs.filter((d) => d.kind === 'sop').length,
      forms: docs.filter((d) => d.kind !== 'sop').length,
      effective: docs.filter((d) => d.kind === 'sop' && d.status === 'Effective').length,
      in_review_or_draft: docs.filter((d) => d.kind === 'sop' && (d.status === 'Draft' || d.status === 'In Review')).length,
      review_due: 0,
    },
    departments: [...new Set(docs.map((d) => d.department).filter((d): d is string => Boolean(d)))],
    fetched_at: '2026-11-05T00:00:00Z',
    from_cache: false,
    source: {
      mode,
      mock_reason: mode === 'mock' ? 'SharePoint credentials are not configured.' : null,
      site_url: mode === 'live' ? 'https://avion.sharepoint.com/sites/Quality' : null,
      library: 'Controlled Documents',
      folder: 'SOPs',
      approved_only: mode === 'live',
    },
  }
}

export function makeSopDetail(
  doc: SopDocument,
  extra: Partial<Pick<SopDetailResponse, 'forms' | 'parent'>> = {},
): SopDetailResponse {
  return {
    document: doc,
    forms: extra.forms ?? [],
    parent: extra.parent ?? null,
    review_due: false,
    source: makeSopList([doc]).source,
  }
}

export const studySource: StudySource = {
  connector: {
    name: 'SimpleTrials',
    mode: 'mock',
    mock_reason: 'SimpleTrials is not connected yet.',
    scope: null,
    base_url: null,
  },
  last_sync: null,
  last_successful_sync_at: '2026-11-05T00:00:00Z',
}

export const RULES = {
  milestone_overdue: 'Overdue: the planned date has passed and SimpleTrials has no actual date.',
  milestone_due_soon: 'Due soon: planned within the next 14 days, not yet completed.',
  enrolment: 'Enrolment: participants enrolled at all sites.',
  risk_score: 'Score: likelihood × impact.',
  task_overdue: 'Overdue task.',
}

export function makeMilestone(overrides: Partial<Milestone> = {}): Milestone {
  return {
    id: overrides.id ?? 'm',
    external_id: overrides.id ?? 'm',
    parent_external_id: null,
    kind: 'milestone',
    is_key: true,
    name: 'Milestone',
    phase: null,
    start_date: null,
    baseline_start_date: null,
    start_variance_days: null,
    planned_date: null,
    actual_date: null,
    baseline_date: null,
    percent_complete: null,
    variance_days: null,
    state: 'upcoming',
    schedule: 'no_baseline',
    ...overrides,
  }
}

export function makeStudy(overrides: Partial<StudySummary> = {}): StudySummary {
  return {
    id: '11111111-1111-1111-1111-111111111111',
    protocol_number: 'DEMO-ONC-301',
    title: 'Phase III oncology demo study',
    sponsor: 'Demo Sponsor A',
    phase: 'Phase III',
    therapeutic_area: 'Oncology',
    status: 'Enrolling',
    countries: ['Australia'],
    project_manager: 'Demo PM One',
    in_source: true,
    sandbox: false,
    synced_at: '2026-11-05T00:00:00Z',
    site_count: 3,
    enrolled: 53,
    enrolment_target: 120,
    enrolment_percent: 44.2,
    overdue_milestones: 1,
    next_milestone: makeMilestone({ id: 'm1', name: '50% enrolled', planned_date: '2026-10-26', state: 'overdue' }),
    open_tasks: 1,
    open_risks: 0,
    ...overrides,
  }
}

export function makeStudyList(studies: StudySummary[]): StudyListResponse {
  return {
    studies,
    total_unfiltered: studies.length,
    statuses: [...new Set(studies.map((s) => s.status).filter((s): s is string => Boolean(s)))],
    phases: [...new Set(studies.map((s) => s.phase).filter((s): s is string => Boolean(s)))],
    source: studySource,
    rules: RULES,
  }
}

export function makeStudyDetail(study: StudySummary): StudyDetailResponse {
  return {
    study,
    sites: [
      {
        id: 's1',
        site_number: '101',
        name: 'Demo Hospital North',
        country: 'Australia',
        principal_investigator: 'Dr Demo Investigator A',
        status: 'Enrolling',
        activation_date: '2026-04-09',
        enrolled: 31,
        enrolment_target: 40,
        enrolment_percent: 77.5,
      },
    ],
    milestones: [
      makeMilestone({ id: 'm0', name: 'First patient in', planned_date: '2026-04-29', actual_date: '2026-05-03', state: 'completed' }),
      study.next_milestone ?? makeMilestone({ id: 'm1', name: 'LPI', state: 'not_planned' }),
    ],
    source: studySource,
    rules: RULES,
  }
}

export function makeTask(overrides: Partial<Task> = {}): Task {
  return {
    id: '22222222-2222-2222-2222-222222222222',
    reference: 'TSK-0001',
    category: 'study',
    category_label: 'Study',
    study: { id: '11111111-1111-1111-1111-111111111111', protocol_number: 'DEMO-ONC-301', title: 'Demo' },
    plan_item: null,
    subject_name: null,
    documents: [],
    title: 'Collect signed CVs for site 102',
    description: null,
    assignees: [{ person_id: 'u1', name: 'Jane Smith', status: 'Not started', completed_at: null }],
    progress: { completed: 0, total: 1 },
    due_date: '2026-11-01',
    status: 'Not started',
    my_status: 'Not started',
    own_task: false,
    overdue: true,
    created_by_name: 'Admin',
    created_at: '2026-11-01T00:00:00Z',
    updated_at: '2026-11-01T00:00:00Z',
    completed_at: null,
    can_update_status: true,
    can_edit: true,
    ...overrides,
  }
}

type Routes = Record<string, unknown | ((url: URL, init?: RequestInit) => unknown)>

/** Stubs fetch: maps "/api/v1/<path>" (without query) to a JSON body or a function of the URL. */
export function mockApi(routes: Routes) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), 'http://localhost')
    const key = url.pathname.replace('/api/v1', '')
    if (!(key in routes)) {
      return new Response(JSON.stringify({ detail: 'Not found' }), { status: 404 })
    }
    const entry = routes[key]
    const body =
      typeof entry === 'function' ? (entry as (u: URL, i?: RequestInit) => unknown)(url, init) : entry
    return new Response(JSON.stringify(body), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

export function renderRoute(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  const client = createQueryClient()
  client.setDefaultOptions({ queries: { retry: false, staleTime: 0 } })
  const result = render(
    <Providers client={client}>
      <RouterProvider router={router} />
    </Providers>,
  )
  return { ...result, router }
}
