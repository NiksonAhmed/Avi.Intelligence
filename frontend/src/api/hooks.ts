import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiRequest } from './client'
import type {
  AuditPage,
  Me,
  SharePointStatus,
  SopDetailResponse,
  SopFilters,
  SopListResponse,
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

export function useSops(filters: SopFilters) {
  return useQuery({
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
