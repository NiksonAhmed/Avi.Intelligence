import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiRequest } from './client'
import type {
  ReportFilters,
  DeviationsReport,
  EtmfReport,
  QualityReport,
  QualityReportFilters,
  StudyDeliveryReport,
  WorkManagementReport,
  WorkReportFilters,
  AskResponse,
  AssistantStatus,
  AuditPage,
  ReindexResponse,
  Me,
  Person,
  Risk,
  RiskFilters,
  RiskInput,
  RiskListResponse,
  RiskStatus,
  SharePointStatus,
  SopDetailResponse,
  SopFilters,
  SopListResponse,
  StudyDetailResponse,
  StudyFilters,
  StudyListResponse,
  StudySource,
  Task,
  TaskFilters,
  TaskInput,
  TaskListResponse,
  TaskStatus,
} from './types'

export const queryKeys = {
  me: ['me'] as const,
  sops: (filters: SopFilters) => ['sops', filters] as const,
  sop: (id: string) => ['sop', id] as const,
  sharepoint: ['connectors', 'sharepoint'] as const,
  audit: (offset: number, limit: number) => ['audit', offset, limit] as const,
}

export function useMe() {
  return useQuery({
    queryKey: queryKeys.me,
    queryFn: () => apiRequest<Me>('/me'),
    staleTime: 5 * 60_000,
  })
}

export function useHasPermission(permission: string): boolean {
  const { data } = useMe()
  return Boolean(data?.permissions.includes(permission))
}

export function useSops(filters: SopFilters, options: { enabled?: boolean } = {}) {
  return useQuery({
    enabled: options.enabled ?? true,
    queryKey: queryKeys.sops(filters),
    queryFn: () =>
      apiRequest<SopListResponse>('/sops', {
        params: { q: filters.q, status: filters.status, department: filters.department },
      }),
    placeholderData: (previous) => previous,
  })
}

export function useSop(id: string) {
  return useQuery({
    queryKey: queryKeys.sop(id),
    queryFn: () => apiRequest<SopDetailResponse>(`/sops/${encodeURIComponent(id)}`),
  })
}

export function useRefreshSops() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => apiRequest<void>('/sops/refresh', { method: 'POST' }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['sops'] })
      await queryClient.invalidateQueries({ queryKey: ['sop'] })
    },
  })
}

export function useSharePointStatus(enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.sharepoint,
    queryFn: () => apiRequest<SharePointStatus>('/connectors/sharepoint'),
    enabled,
    staleTime: 0,
  })
}

export function useAssistantStatus(enabled = true) {
  return useQuery({
    queryKey: ['assistant', 'status'],
    queryFn: () => apiRequest<AssistantStatus>('/assistant/status'),
    enabled,
  })
}

export function useAsk() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (question: string) =>
      apiRequest<AskResponse>('/assistant/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
      }),
    // The first question builds the index, so status counts change.
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['assistant', 'status'] }),
  })
}

export function useReindex() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => apiRequest<ReindexResponse>('/assistant/reindex', { method: 'POST' }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['assistant'] }),
  })
}

// --- Studies ---------------------------------------------------------------------------------

const jsonInit = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export function useStudies(filters: StudyFilters = {}) {
  return useQuery({
    queryKey: ['studies', filters],
    queryFn: () =>
      apiRequest<StudyListResponse>('/studies', {
        params: { q: filters.q, status: filters.status, phase: filters.phase },
      }),
    placeholderData: (previous) => previous,
  })
}

export function useStudy(id: string | undefined) {
  return useQuery({
    queryKey: ['study', id],
    queryFn: () => apiRequest<StudyDetailResponse>(`/studies/${encodeURIComponent(id ?? '')}`),
    enabled: Boolean(id),
  })
}

export function useSimpleTrialsStatus(enabled: boolean) {
  return useQuery({
    queryKey: ['connectors', 'simpletrials'],
    queryFn: () => apiRequest<StudySource>('/connectors/simpletrials'),
    enabled,
  })
}

export function useSyncSimpleTrials() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => apiRequest<StudySource>('/connectors/simpletrials/sync', { method: 'POST' }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['connectors', 'simpletrials'] })
      await queryClient.invalidateQueries({ queryKey: ['studies'] })
      await queryClient.invalidateQueries({ queryKey: ['study'] })
    },
  })
}

export function usePeople() {
  return useQuery({
    queryKey: ['people'],
    queryFn: () => apiRequest<Person[]>('/people'),
    staleTime: 10 * 60_000,
  })
}

// --- Tasks and risks ---------------------------------------------------------------------------

/** Task and risk changes also change the open counts shown on study screens. */
async function invalidateWork(queryClient: ReturnType<typeof useQueryClient>, key: 'tasks' | 'risks') {
  await queryClient.invalidateQueries({ queryKey: [key] })
  await queryClient.invalidateQueries({ queryKey: ['studies'] })
  await queryClient.invalidateQueries({ queryKey: ['study'] })
}

export function useTasks(filters: TaskFilters) {
  return useQuery({
    queryKey: ['tasks', filters],
    queryFn: () =>
      apiRequest<TaskListResponse>('/tasks', {
        params: {
          study_id: filters.study_id,
          assignee: filters.assignee,
          category: filters.category,
          sop_id: filters.sop_id,
          include_closed: filters.include_closed ? 'true' : undefined,
        },
      }),
    placeholderData: (previous) => previous,
  })
}

export function useCreateTask() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: TaskInput) => apiRequest<Task>('/tasks', jsonInit('POST', input)),
    onSuccess: () => invalidateWork(queryClient, 'tasks'),
  })
}

export function useUpdateTask() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: Partial<TaskInput> & { status?: TaskStatus } }) =>
      apiRequest<Task>(`/tasks/${encodeURIComponent(id)}`, jsonInit('PATCH', input)),
    onSuccess: () => invalidateWork(queryClient, 'tasks'),
  })
}

export function useTaskStatus() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, status, personId }: { id: string; status: TaskStatus; personId?: string }) =>
      apiRequest<Task>(
        `/tasks/${encodeURIComponent(id)}/status`,
        jsonInit('POST', personId ? { status, person_id: personId } : { status }),
      ),
    onSuccess: () => invalidateWork(queryClient, 'tasks'),
  })
}

export function useRisks(filters: RiskFilters) {
  return useQuery({
    queryKey: ['risks', filters],
    queryFn: () =>
      apiRequest<RiskListResponse>('/risks', {
        params: {
          study_id: filters.study_id,
          kind: filters.kind,
          owner: filters.owner,
          include_closed: filters.include_closed ? 'true' : undefined,
        },
      }),
    placeholderData: (previous) => previous,
  })
}

export function useCreateRisk() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: RiskInput) => apiRequest<Risk>('/risks', jsonInit('POST', input)),
    onSuccess: () => invalidateWork(queryClient, 'risks'),
  })
}

export function useUpdateRisk() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: Partial<RiskInput> & { status?: RiskStatus } }) =>
      apiRequest<Risk>(`/risks/${encodeURIComponent(id)}`, jsonInit('PATCH', input)),
    onSuccess: () => invalidateWork(queryClient, 'risks'),
  })
}

export function useRiskStatus() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, status }: { id: string; status: RiskStatus }) =>
      apiRequest<Risk>(`/risks/${encodeURIComponent(id)}/status`, jsonInit('POST', { status })),
    onSuccess: () => invalidateWork(queryClient, 'risks'),
  })
}

export function useAuditEvents(offset: number, limit: number, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.audit(offset, limit),
    queryFn: () =>
      apiRequest<AuditPage>('/audit-events', {
        params: { offset: String(offset), limit: String(limit) },
      }),
    enabled,
    placeholderData: (previous) => previous,
  })
}

export function useDeviationsReport(filters: ReportFilters) {
  return useQuery({
    queryKey: ['reports', 'deviations', filters],
    queryFn: () =>
      apiRequest<DeviationsReport>('/reports/deviations', { params: { study_id: filters.study_id, site_id: filters.site_id } }),
    placeholderData: (previous) => previous,
  })
}

export function useEtmfReport(filters: ReportFilters) {
  return useQuery({
    queryKey: ['reports', 'etmf', filters],
    queryFn: () =>
      apiRequest<EtmfReport>('/reports/etmf', { params: { study_id: filters.study_id, site_id: filters.site_id } }),
    placeholderData: (previous) => previous,
  })
}

export function useQualityReport(filters: QualityReportFilters) {
  return useQuery({
    queryKey: ['reports', 'quality', filters],
    queryFn: () =>
      apiRequest<QualityReport>('/reports/quality', {
        params: { department: filters.department, months: filters.months ? String(filters.months) : undefined },
      }),
    placeholderData: (previous) => previous,
  })
}

export function useWorkManagement(filters: WorkReportFilters) {
  return useQuery({
    queryKey: ['reports', 'work-management', filters],
    queryFn: () =>
      apiRequest<WorkManagementReport>('/reports/work-management', {
        params: { study_id: filters.study_id, category: filters.category },
      }),
    placeholderData: (previous) => previous,
  })
}

export function useStudyDelivery(filters: ReportFilters) {
  return useQuery({
    queryKey: ['reports', 'study-delivery', filters],
    queryFn: () =>
      apiRequest<StudyDeliveryReport>('/reports/study-delivery', {
        params: { study_id: filters.study_id, site_id: filters.site_id },
      }),
    placeholderData: (previous) => previous,
  })
}
