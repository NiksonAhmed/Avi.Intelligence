import { render } from '@testing-library/react'
import { createMemoryRouter } from 'react-router'
import { RouterProvider } from 'react-router/dom'
import { vi } from 'vitest'

import type { Me, SopDetailResponse, SopDocument, SopListResponse } from '../api/types'
import { Providers } from '../Providers'
import { createQueryClient } from '../lib/queryClient'
import { routes } from '../router'

export const adminUser: Me = {
  id: 'u1',
  name: 'Jane Smith',
  email: 'jane@example.com',
  role: 'admin',
  role_label: 'Administrator',
  permissions: ['audit.read', 'connector.manage', 'sop.download', 'sop.read'],
  auth_mode: 'development',
}

export const viewerUser: Me = {
  ...adminUser,
  role: 'viewer',
  role_label: 'Viewer',
  permissions: ['sop.read'],
}

export function makeSop(overrides: Partial<SopDocument> = {}): SopDocument {
  return {
    id: 'demo-sop-011',
    title: 'Site Activation',
    file_name: 'SOP-011 Site Activation v3.0.docx',
    sop_number: 'SOP-011',
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
      total: docs.length,
      effective: docs.filter((d) => d.status === 'Effective').length,
      in_review_or_draft: docs.filter((d) => d.status === 'Draft' || d.status === 'In Review').length,
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
    },
  }
}

export function makeSopDetail(doc: SopDocument): SopDetailResponse {
  return {
    document: doc,
    versions: [{ id: '3.0', modified_at: doc.modified_at, modified_by: 'QA', size_bytes: 1 }],
    review_due: false,
    source: makeSopList([doc]).source,
  }
}

type Routes = Record<string, unknown | ((url: URL) => unknown)>

/** Stubs fetch: maps "/api/v1/<path>" (without query) to a JSON body or a function of the URL. */
export function mockApi(routes: Routes) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), 'http://localhost')
    const key = url.pathname.replace('/api/v1', '')
    if (!(key in routes)) {
      return new Response(JSON.stringify({ detail: 'Not found' }), { status: 404 })
    }
    const entry = routes[key]
    const body = typeof entry === 'function' ? (entry as (u: URL) => unknown)(url) : entry
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
