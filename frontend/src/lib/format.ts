/** Display formatting. SharePoint stores date-only columns as UTC instants, so dates are shown
 * in the organisation's time zone to avoid off-by-one-day errors. */

export const APP_TIME_ZONE: string =
  (import.meta.env.VITE_APP_TIME_ZONE as string | undefined) ?? 'Australia/Sydney'

const dateFormat = new Intl.DateTimeFormat('en-AU', {
  timeZone: APP_TIME_ZONE,
  day: '2-digit',
  month: 'short',
  year: 'numeric',
})

const dateTimeFormat = new Intl.DateTimeFormat('en-AU', {
  timeZone: APP_TIME_ZONE,
  day: '2-digit',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
})

function toDate(value: string | null | undefined): Date | null {
  if (!value) return null
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? null : d
}

export function formatDate(value: string | null | undefined): string {
  const d = toDate(value)
  return d ? dateFormat.format(d) : '—'
}

export function formatDateTime(value: string | null | undefined): string {
  const d = toDate(value)
  return d ? dateTimeFormat.format(d) : '—'
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('')
}
