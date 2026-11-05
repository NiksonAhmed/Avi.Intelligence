/** Mirrors the backend response models (backend/src/app/api, connectors/sharepoint/models.py). */

export const SOP_STATUSES = [
  'Effective',
  'In Review',
  'Draft',
  'Superseded',
  'Retired',
  'Unknown',
] as const

export type SopStatus = (typeof SOP_STATUSES)[number]

export type StatusSource = 'column' | 'content-approval' | 'version-number' | 'none'

export interface SopDocument {
  id: string
  title: string
  file_name: string
  sop_number: string | null
  version: string | null
  status: SopStatus
  status_source: StatusSource
  effective_date: string | null
  review_date: string | null
  owner: string | null
  department: string | null
  folder_path: string
  modified_at: string | null
  modified_by: string | null
  web_url: string | null
  size_bytes: number | null
  mime_type: string | null
}

export interface SopVersion {
  id: string
  modified_at: string | null
  modified_by: string | null
  size_bytes: number | null
}

export interface SopSource {
  mode: 'live' | 'mock'
  mock_reason: string | null
  site_url: string | null
  library: string
  folder: string | null
}

export interface SopSummary {
  total: number
  effective: number
  in_review_or_draft: number
  review_due: number
}

export interface SopListResponse {
  documents: SopDocument[]
  total_unfiltered: number
  summary: SopSummary
  departments: string[]
  fetched_at: string
  from_cache: boolean
  source: SopSource
}

export interface SopDetailResponse {
  document: SopDocument
  versions: SopVersion[]
  review_due: boolean
  source: SopSource
}

export interface SopFilters {
  q?: string
  status?: SopStatus
  department?: string
}

export interface Me {
  id: string
  name: string
  email: string
  role: string
  role_label: string
  permissions: string[]
  auth_mode: string
}

export interface CheckStep {
  label: string
  ok: boolean
  detail: string | null
}

export interface ConnectorColumn {
  name: string
  display_name: string
  type: string
}

export interface SharePointStatus {
  info: SopSource & { field_map: Record<string, string[]> }
  check: {
    ok: boolean
    steps: CheckStep[]
    columns: ConnectorColumn[] | null
    document_count: number | null
  }
}

export interface AuditEvent {
  id: string
  occurred_at: string
  actor_name: string
  actor_role: string
  action: string
  entity_type: string
  entity_id: string | null
  summary: string
  details: Record<string, unknown>
}

export interface AuditPage {
  items: AuditEvent[]
  total: number
}
