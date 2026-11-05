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

export interface AssistantCitation {
  number: number
  sop_id: string
  sop_number: string | null
  title: string
  version: string | null
  section: string
  cited_text: string
  web_url: string | null
}

export interface AnswerSegment {
  text: string
  citations: number[]
}

export interface AssistantExcerpt {
  sop_id: string
  sop_number: string | null
  title: string
  version: string | null
  section: string
  text: string
}

export interface AskResponse {
  interaction_id: string
  mode: 'ai' | 'search-only'
  outcome: 'answered' | 'refused' | 'no-sources'
  segments: AnswerSegment[]
  citations: AssistantCitation[]
  excerpts: AssistantExcerpt[]
  notice: string | null
  model: string | null
  demo: boolean
}

export interface AssistantStatus {
  ai_enabled: boolean
  model: string | null
  demo: boolean
  documents: number
  passages: number
  failed: number
  last_indexed_at: string | null
  suggested_questions: string[]
}

export interface ReindexResponse {
  indexed: number
  unchanged: number
  removed: number
  failed: { sop: string; reason: string }[]
  documents: { sop_number: string | null; title: string; version: string | null; passages: number; error: string | null }[]
}

export interface AuditPage {
  items: AuditEvent[]
  total: number
}

// --- Studies (read-only copy of SimpleTrials) -------------------------------------------------

export type MilestoneState = 'completed' | 'overdue' | 'due_soon' | 'upcoming' | 'not_planned'

export interface SyncInfo {
  started_at: string
  finished_at: string | null
  ok: boolean
  mode: string
  counts: Record<string, number>
  error: string | null
  triggered_by: string
}

export interface StudySource {
  connector: { name: string; mode: 'mock' | 'import' | 'api'; mock_reason: string | null }
  last_sync: SyncInfo | null
  last_successful_sync_at: string | null
}

export interface Milestone {
  id: string
  name: string
  planned_date: string | null
  actual_date: string | null
  state: MilestoneState
}

export interface StudySite {
  id: string
  site_number: string
  name: string
  country: string | null
  principal_investigator: string | null
  status: string | null
  activation_date: string | null
  enrolled: number | null
  enrolment_target: number | null
  enrolment_percent: number | null
}

export interface StudySummary {
  id: string
  protocol_number: string
  title: string
  sponsor: string | null
  phase: string | null
  therapeutic_area: string | null
  status: string | null
  countries: string[]
  project_manager: string | null
  in_source: boolean
  synced_at: string
  site_count: number
  enrolled: number | null
  enrolment_target: number | null
  enrolment_percent: number | null
  overdue_milestones: number
  next_milestone: Milestone | null
  open_tasks: number
  open_risks: number
}

export type Rules = Record<string, string>

export interface StudyListResponse {
  studies: StudySummary[]
  total_unfiltered: number
  statuses: string[]
  phases: string[]
  source: StudySource
  rules: Rules
}

export interface StudyDetailResponse {
  study: StudySummary
  sites: StudySite[]
  milestones: Milestone[]
  source: StudySource
  rules: Rules
}

export interface StudyFilters {
  q?: string
  status?: string
  phase?: string
}

// --- Tasks, risks and issues (managed in Avi.Intelligence) ------------------------------------

export interface Person {
  id: string
  name: string
  email: string
  job_title: string
  demo: boolean
}

export interface StudyRef {
  id: string
  protocol_number: string
  title: string
}

export const TASK_STATUSES = ['Not started', 'In progress', 'Blocked', 'Completed', 'Cancelled'] as const
export type TaskStatus = (typeof TASK_STATUSES)[number]

export interface Task {
  id: string
  reference: string
  study: StudyRef
  title: string
  description: string | null
  assignee_id: string
  assignee_name: string
  due_date: string | null
  status: TaskStatus
  overdue: boolean
  created_by_name: string
  created_at: string
  updated_at: string
  completed_at: string | null
  can_update_status: boolean
}

export interface TaskListResponse {
  tasks: Task[]
  can_manage: boolean
  statuses: TaskStatus[]
}

export interface TaskFilters {
  study_id?: string
  assignee?: string
  include_closed?: boolean
}

export interface TaskInput {
  study_id: string
  title: string
  description?: string | null
  assignee_id: string
  due_date?: string | null
}

export const RISK_STATUSES = ['Open', 'Mitigating', 'Closed'] as const
export type RiskStatus = (typeof RISK_STATUSES)[number]
export type RiskKind = 'risk' | 'issue'

export interface Risk {
  id: string
  reference: string
  kind: RiskKind
  study: StudyRef
  title: string
  description: string | null
  likelihood: number
  impact: number
  score: number
  rating: 'Low' | 'Medium' | 'High'
  mitigation: string | null
  owner_id: string
  owner_name: string
  status: RiskStatus
  created_by_name: string
  created_at: string
  updated_at: string
  closed_at: string | null
  can_update_status: boolean
}

export interface RiskListResponse {
  risks: Risk[]
  can_manage: boolean
  statuses: RiskStatus[]
}

export interface RiskFilters {
  study_id?: string
  kind?: RiskKind
  owner?: string
  include_closed?: boolean
}

export interface RiskInput {
  study_id: string
  kind: RiskKind
  title: string
  description?: string | null
  likelihood: number
  impact: number
  mitigation?: string | null
  owner_id: string
}
