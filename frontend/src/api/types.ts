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

export type StatusSource = 'column' | 'folder' | 'content-approval' | 'version-number' | 'none'

export interface RevisionEntry {
  issued: string | null
  version: string
  changes: string
}

/** Document control details read from inside the document (cover page and change history). */
export interface DocumentDetails {
  version: string | null
  effective_date: string | null
  review_date: string | null
  prepared_by: string | null
  prepared_date: string | null
  reviewed_by: string | null
  reviewed_date: string | null
  approved_by: string | null
  approved_date: string | null
  revisions: RevisionEntry[]
}

/** An SOP, or a form/template belonging to an SOP (e.g. CO-005-A under CO-SOP-005). */
export type DocumentKind = 'sop' | 'form' | 'other'

export interface SopDocument {
  id: string
  title: string
  file_name: string
  sop_number: string | null
  kind: DocumentKind
  parent_sop_number: string | null
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
  /** Read from inside the document when it was indexed (approved SOPs only). */
  details?: DocumentDetails | null
  version_source?: 'column' | 'document' | 'file-name' | null
  /** Set when the file name states a different version than the document itself. */
  file_name_version?: string | null
  /** Word copy filed next to the signed PDF; offered as a download for forms/templates. */
  editable_copy?: { id: string; file_name: string; size_bytes: number | null; mime_type: string | null } | null
}


export interface SopSource {
  mode: 'live' | 'mock'
  mock_reason: string | null
  site_url: string | null
  library: string
  folder: string | null
  /** Only approved documents are listed; drafts and superseded versions are never shown. */
  approved_only: boolean
}

export interface SopSummary {
  /** SOPs only; forms and templates are counted in `forms`. */
  total: number
  forms: number
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
  /** For an SOP: its forms and templates. */
  forms: SopDocument[]
  /** For a form or template: the SOP it belongs to. */
  parent: SopDocument | null
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

export interface StudyAnswerTable {
  title: string
  columns: string[]
  rows: string[][]
  /** Per row: where the record is shown in Avi.Intelligence. */
  links: (string | null)[]
  /** Rows not shown (the table is capped). */
  more: number
}

/** A study question answered from the SimpleTrials copy by fixed rules (no AI). */
export interface StudyAnswer {
  intent: 'status' | 'due' | 'behind' | 'milestone' | 'enrolment' | 'activation' | 'tasks' | 'risks'
  /** How the question was read, e.g. "What is due · close-out · next 90 days · all studies". */
  understood: string
  headline: string
  lines: string[]
  tables: StudyAnswerTable[]
  sources: { label: string; url: string }[]
  as_of: string | null
  sandbox_only: boolean
  follow_ups: string[]
  note: string
}

export interface AskResponse {
  interaction_id: string
  mode: 'ai' | 'search-only' | 'study-lookup'
  outcome: 'answered' | 'refused' | 'no-sources'
  segments: AnswerSegment[]
  citations: AssistantCitation[]
  excerpts: AssistantExcerpt[]
  notice: string | null
  model: string | null
  demo: boolean
  kind: 'sop' | 'study'
  study: StudyAnswer | null
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
  /** Example study questions (empty when the user cannot see studies). */
  study_questions: string[]
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

/** Progress status: against the current end date. */
export type MilestoneState =
  | 'completed'
  | 'overdue'
  | 'due_soon'
  | 'in_progress'
  | 'not_started'
  | 'upcoming'
  | 'not_planned'

/** Schedule status: current end date compared with the original (baseline) end date. */
export type ScheduleState = 'on_plan' | 'slipped' | 'slipped_major' | 'ahead' | 'no_baseline'

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
  connector: {
    name: string
    mode: 'mock' | 'import' | 'api'
    mock_reason: string | null
    scope: 'workspace' | 'study' | null
    base_url: string | null
  }
  last_sync: SyncInfo | null
  last_successful_sync_at: string | null
}

/** One entry of the study plan (phase, task or milestone), in SimpleTrials order. */
export interface Milestone {
  id: string
  external_id: string
  parent_external_id: string | null
  kind: 'phase' | 'task' | 'milestone'
  is_key: boolean
  name: string
  phase: string | null
  /** Current start date. */
  start_date: string | null
  /** Original (baseline) start date. */
  baseline_start_date: string | null
  /** Current start minus original start, in days (positive = later). */
  start_variance_days: number | null
  /** Current end date. */
  planned_date: string | null
  actual_date: string | null
  /** Original (baseline) end date. */
  baseline_date: string | null
  percent_complete: number | null
  /** Current end minus original end, in days (positive = later). */
  variance_days: number | null
  state: MilestoneState
  schedule: ScheduleState
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
  sandbox: boolean
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

/** The study-plan entry (SimpleTrials milestone/task) a task was raised for. */
export interface PlanItemRef {
  external_id: string
  name: string
}

/** What a task is about. Study tasks link to a study, SOP tasks to approved SOPs/forms. */
export type TaskCategory = 'study' | 'sop' | 'vendor' | 'system' | 'general'

export const TASK_CATEGORY_LABELS: Record<TaskCategory, string> = {
  study: 'Study',
  sop: 'Procedures and SOPs',
  vendor: 'Vendor',
  system: 'Computer system',
  general: 'General',
}

export interface TaskAssignee {
  person_id: string
  name: string
  status: TaskStatus
  completed_at: string | null
}

/** An approved SOP or form, as it was when the task was raised. */
export interface TaskDocumentRef {
  sop_id: string
  kind: string
  sop_number: string | null
  title: string
  version: string | null
}

export interface Task {
  id: string
  reference: string
  category: TaskCategory
  category_label: string
  study: StudyRef | null
  plan_item: PlanItemRef | null
  /** Vendor or computer system name, as typed. */
  subject_name: string | null
  documents: TaskDocumentRef[]
  title: string
  description: string | null
  /** Everyone the task is assigned to, each with their own status. */
  assignees: TaskAssignee[]
  progress: { completed: number; total: number }
  due_date: string | null
  /** Overall: Completed when everyone is done; Cancelled when the task was cancelled. */
  status: TaskStatus
  /** The current user's own status, when they are one of the assigned people. */
  my_status: TaskStatus | null
  /** Created by someone for themselves. */
  own_task: boolean
  overdue: boolean
  created_by_name: string
  created_at: string
  updated_at: string
  completed_at: string | null
  can_update_status: boolean
  can_edit: boolean
}

export interface TaskListResponse {
  tasks: Task[]
  /** Administrator: manages every task. */
  can_manage: boolean
  /** Categories the current user may create tasks in (empty = read-only). */
  can_create: TaskCategory[]
  /** Categories the current user may assign to other people; others are for themselves only. */
  can_assign: TaskCategory[]
  categories: { value: TaskCategory; label: string }[]
  statuses: TaskStatus[]
}

export interface TaskFilters {
  study_id?: string
  assignee?: string
  category?: TaskCategory
  sop_id?: string
  include_closed?: boolean
}

export interface TaskInput {
  category?: TaskCategory
  study_id?: string | null
  plan_item_id?: string | null
  subject_name?: string | null
  document_ids?: string[]
  title: string
  description?: string | null
  assignee_ids: string[]
  due_date?: string | null
}

/** A SimpleTrials action item shown as a read-only issue (managed in SimpleTrials). */
export interface SimpleTrialsIssue {
  id: string
  number: string | null
  study: StudyRef
  site_number: string | null
  site_name: string | null
  category: string | null
  subcategory: string | null
  priority: string | null
  status: string | null
  closed: boolean
  description: string | null
  response: string | null
  assignee: string | null
  opened_on: string | null
  due_on: string | null
  closed_on: string | null
  /** Days past the due date for open items; null when not overdue. */
  days_overdue: number | null
}

/** Risks and issues come from SimpleTrials (the CTMS) only; nothing is raised in Avi.Intelligence. */
export interface RiskListResponse {
  simpletrials_issues: SimpleTrialsIssue[]
}

export interface RiskFilters {
  study_id?: string
  include_closed?: boolean
}


// ---- Reports and Insights ----

export type ReportTone = 'good' | 'info' | 'warn' | 'bad' | 'neutral'

export interface ReportTile {
  key: string
  label: string
  value: string
  note: string
  tone: ReportTone
}

export interface ReportOption {
  id: string
  label: string
}

export interface ReportSource {
  /** "api" (SimpleTrials) or "mock" (demo data). */
  mode: string
  /** When the data was last copied from SimpleTrials. */
  as_of: string | null
  sandbox_only: boolean
  /** Days of history kept so far (trend charts need a few weeks). */
  snapshot_days: number
}

export interface DeliveryMilestone {
  study_id: string
  protocol_number: string
  name: string
  original_date: string | null
  current_date: string | null
  variance_days: number | null
  state: MilestoneState
  schedule: ScheduleState
  completed_on: string | null
  completion_basis: 'actual' | 'first-seen' | 'before-tracking' | null
  on_time: boolean | null
}

export interface DeliverySite {
  study_id: string
  protocol_number: string
  site_id: string
  site_number: string
  name: string
  country: string | null
  enrolled: number | null
  target: number | null
  percent: number | null
  flag: 'none' | 'zero' | 'no_target' | 'over_target'
}

export interface PendingSite {
  study_id: string
  protocol_number: string
  site_id: string
  site_number: string
  name: string
  status: string | null
  planned_date: string | null
  days_late: number | null
  state: 'late' | 'due_soon' | 'upcoming' | 'no_date'
}

export interface StudyDeliveryReport {
  tiles: ReportTile[]
  milestones: DeliveryMilestone[]
  on_time: { completed: number; on_time: number; with_original_date: number }
  sites: DeliverySite[]
  activation: { total: number; activated: number; percent: number | null; with_target: number; on_time: number }
  pending_sites: PendingSite[]
  study_options: ReportOption[]
  site_options: ReportOption[]
  rules: Record<string, string>
  source: ReportSource
}

export interface ReportFilters {
  study_id?: string
  site_id?: string
}

export interface WorkStatusCounts {
  key: string
  label: string
  not_started: number
  in_progress: number
  blocked: number
  overdue: number
  total: number
}

export interface WorkPersonLoad {
  person_id: string
  name: string
  open: number
  overdue: number
  due_soon: number
  blocked: number
}

export interface WorkOverdueTask {
  task_id: string
  reference: string
  title: string
  category: TaskCategory
  category_label: string
  about: string | null
  due_date: string
  days_overdue: number
  status: TaskStatus
  /** People who have not finished their part yet. */
  waiting_on: string[]
}

export interface WorkManagementReport {
  tiles: ReportTile[]
  by_category: WorkStatusCounts[]
  by_study: WorkStatusCounts[]
  by_person: WorkPersonLoad[]
  overdue: WorkOverdueTask[]
  completed: { total: number; with_due_date: number; on_time: number }
  study_options: ReportOption[]
  category_options: ReportOption[]
  rules: Record<string, string>
  source: ReportSource
}

export interface EtmfCompleteness {
  key: string
  label: string
  expected: number
  filed: number
  missing: number
  percent: number | null
}

export interface EtmfHeatRow {
  site_id: string
  label: string
  protocol_number: string
  cells: EtmfCompleteness[]
}

export interface EtmfExpiring {
  id: string
  name: string
  protocol_number: string
  /** The site, or "Study level". */
  where: string
  expires_on: string
  /** Days until expiry (negative: expired that many days ago). */
  days: number
  state: 'expired' | 'expiring'
}

export interface EtmfReport {
  tiles: ReportTile[]
  overall: EtmfCompleteness
  by_study: EtmfCompleteness[]
  sites_missing: EtmfCompleteness[]
  sections: string[]
  heat_map: EtmfHeatRow[]
  qc: { label: string; count: number }[]
  timeliness: { key: string; label: string; count: number }[]
  timeliness_measured: number
  timeliness_on_time: number
  expiring: EtmfExpiring[]
  missing_documents: { protocol_number: string; where: string; section: string; folder: string | null; name: string }[]
  has_documents: boolean
  study_options: ReportOption[]
  site_options: ReportOption[]
  rules: Record<string, string>
  source: ReportSource
}

export interface DeviationCount {
  key: string
  label: string
  count: number
  open: number
}

export interface DeviationRow {
  id: string
  number: string | null
  protocol_number: string
  where: string
  category: string
  severity: string
  status: string
  closed: boolean
  description: string | null
  subject_level: boolean
  occurred_on: string | null
  identified_on: string | null
  reported_on: string | null
  closed_on: string | null
  reportable: boolean | null
  days_open: number | null
  days_to_identify: number | null
}

/** Protocol deviations report: SimpleTrials deviations (read-only copy; no subject IDs or people). */
export interface DeviationsReport {
  tiles: ReportTile[]
  by_severity: DeviationCount[]
  by_category: DeviationCount[]
  by_site: { key: string; label: string; protocol_number: string; total: number; open: number; major: number; enrolled: number | null; per_10: number | null }[]
  trend: { month: string; critical: number; major: number; minor: number; other: number }[]
  ageing: DeviationCount[]
  deviations: DeviationRow[]
  has_deviations: boolean
  study_options: ReportOption[]
  site_options: ReportOption[]
  rules: Record<string, string>
  source: ReportSource
}

export interface IssueRow {
  id: string
  number: string | null
  protocol_number: string
  where: string
  category: string
  subcategory: string | null
  priority: string
  status: string
  closed: boolean
  description: string | null
  response: string | null
  assignee: string | null
  opened_on: string | null
  due_on: string | null
  closed_on: string | null
  days_open: number | null
  days_overdue: number | null
}

/** Risks and issues report: SimpleTrials action items (read-only copy; nothing raised in Avi.Intelligence). */
export interface RisksIssuesReport {
  tiles: ReportTile[]
  by_priority: (DeviationCount & { overdue: number })[]
  by_category: DeviationCount[]
  by_site: { key: string; label: string; protocol_number: string; open: number; overdue: number; total: number }[]
  ageing: DeviationCount[]
  trend: { month: string; opened: number; closed: number }[]
  issues: IssueRow[]
  has_issues: boolean
  study_options: ReportOption[]
  site_options: ReportOption[]
  rules: Record<string, string>
  source: ReportSource
}

export type OverviewTone = 'good' | 'info' | 'warn' | 'bad' | 'neutral'

export interface OverviewKpi {
  label: string
  value: string
  note: string | null
  tone: OverviewTone
  /** Opens the page with the detail. */
  link: string | null
}

export interface OverviewRow {
  label: string
  detail: string | null
  chip: string | null
  tone: OverviewTone
  link: string | null
}

export interface OverviewSection {
  key: string
  title: string
  source: string
  link: string | null
  link_label: string | null
  kpis: OverviewKpi[]
  rows: OverviewRow[]
  notice: string | null
  empty: string | null
}

/** The role-based Overview: each role sees its own page; administrators may preview any role. */
export interface OverviewData {
  view: string
  view_label: string
  views: { id: string; label: string }[]
  purpose: string
  sources: { name: string; as_of: string | null; ok: boolean }[]
  attention: { counts: OverviewKpi[]; items: OverviewRow[] }
  sections: OverviewSection[]
}

/** Which sites each person (CRA) covers; set by administrators (SimpleTrials does not record it). */
export interface SiteAssignments {
  people: { id: string; name: string; job_title: string }[]
  sites: { key: string; label: string }[]
  assignments: Record<string, string[]>
}

export type ReviewState = 'overdue' | 'due_soon' | 'scheduled' | 'no_date'

export interface QualityScheduleRow {
  id: string
  sop_number: string | null
  title: string
  version: string | null
  department: string | null
  owner: string | null
  effective_date: string | null
  review_date: string | null
  days_to_review: number | null
  state: ReviewState
  forms: number
  open_tasks: number
}

export interface QualityMonth {
  /** "overdue", or the month as YYYY-MM. */
  key: string
  label: string
  count: number
  items: string[]
}

export interface QualityHealthCheck {
  key: string
  label: string
  description: string
  count: number
  items: { id: string; label: string }[]
}

export interface QualityChange {
  id: string
  sop_number: string | null
  title: string
  kind: 'sop' | 'form' | 'other'
  version: string
  issued: string
  changes: string | null
  basis: 'history' | 'effective'
}

export interface QualityReport {
  tiles: ReportTile[]
  schedule: QualityScheduleRow[]
  by_month: QualityMonth[]
  /** Reviews due after the months shown. */
  later: number
  health: QualityHealthCheck[]
  changes: QualityChange[]
  months: number
  department_options: ReportOption[]
  rules: Record<string, string>
  source: { mode: string; approved_only: boolean; library: string }
  fetched_at: string
}

export interface QualityReportFilters {
  department?: string
  months?: number
}

export interface WorkReportFilters {
  study_id?: string
  category?: TaskCategory
}
