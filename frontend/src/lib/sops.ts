import type { SopDocument, StatusSource } from '../api/types'

const REVIEW_WINDOW_MS = 30 * 24 * 60 * 60 * 1000

/** Effective SOPs whose review date is past or within the next 30 days (matches the API summary). */
export function isReviewDue(doc: SopDocument, now = Date.now()): boolean {
  if (doc.status !== 'Effective' || !doc.review_date) return false
  return new Date(doc.review_date).getTime() <= now + REVIEW_WINDOW_MS
}

export const STATUS_SOURCE_TEXT: Record<StatusSource, string> = {
  column: "Taken from the library's status column in SharePoint.",
  'content-approval': 'Taken from SharePoint content approval.',
  'version-number':
    'Inferred from the SharePoint version number (major versions are treated as published).',
  none: 'SharePoint holds no status information for this document.',
}
