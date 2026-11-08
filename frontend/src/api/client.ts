/** Thin fetch wrapper for the Avi.Intelligence API (same origin; Vite proxies /api in development). */

export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function parseError(res: Response): Promise<ApiError> {
  let message = `Request failed (HTTP ${res.status}).`
  try {
    const body: unknown = await res.json()
    if (body && typeof body === 'object' && 'detail' in body) {
      const detail = (body as { detail: unknown }).detail
      if (typeof detail === 'string') message = detail
    }
  } catch {
    // non-JSON error body; keep the generic message
  }
  return new ApiError(message, res.status)
}

export async function apiRequest<T>(
  path: string,
  init: RequestInit & { params?: Record<string, string | undefined> } = {},
): Promise<T> {
  const { params, ...rest } = init
  const url = new URL(`/api/v1${path}`, window.location.origin)
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value) url.searchParams.set(key, value)
  }
  const res = await fetch(url.pathname + url.search, {
    ...rest,
    headers: { Accept: 'application/json', ...(rest.headers ?? {}) },
  })
  if (!res.ok) throw await parseError(res)
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

/** format "word": the Word copy of a form/template (for filling in). */
export function sopDownloadUrl(id: string, format: 'original' | 'word' = 'original'): string {
  const url = `/api/v1/sops/${encodeURIComponent(id)}/download`
  return format === 'word' ? `${url}?format=word` : url
}

/** Excel export of a report, with the same filters as on screen. */
export function reportExportUrl(report: 'study-delivery', filters: Record<string, string | undefined>): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) if (value) params.set(key, value)
  const query = params.toString()
  return `/api/v1/reports/${report}/export.xlsx${query ? `?${query}` : ''}`
}
