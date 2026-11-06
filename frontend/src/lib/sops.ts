import type { SopDocument, StatusSource } from '../api/types'

const REVIEW_WINDOW_MS = 30 * 24 * 60 * 60 * 1000

/** Effective SOPs whose review date is past or within the next 30 days (matches the API summary). */
export function isReviewDue(doc: SopDocument, now = Date.now()): boolean {
  if (doc.status !== 'Effective' || !doc.review_date) return false
  return new Date(doc.review_date).getTime() <= now + REVIEW_WINDOW_MS
}

const isWordFile = (name: string) => /\.docx?$/i.test(name)

/** Which downloads to offer: forms/templates get a Word file (for filling in) where one is filed. */
export function downloadOptions(doc: SopDocument): { word: boolean; original: boolean; originalLabel: string } {
  const originalIsWord = isWordFile(doc.file_name)
  const word = doc.kind === 'form' && (Boolean(doc.editable_copy) || originalIsWord)
  const ext = doc.file_name.split('.').pop()?.toUpperCase() ?? 'file'
  return {
    word,
    // A form filed only as Word needs just the one button.
    original: !(word && originalIsWord),
    originalLabel: ext === 'PDF' ? 'PDF' : ext,
  }
}

export type SopRow =SopDocument & { children?: SopRow[] }

/**
 * Nests each form/template under its SOP (e.g. CO-005-A under CO-SOP-005) when that SOP is in the
 * list; forms without their SOP in the list stay at the top level. Order is kept.
 */
export function toSopTree(docs: SopDocument[]): SopRow[] {
  const sops = new Map<string, SopRow>()
  for (const d of docs) if (d.kind === 'sop' && d.sop_number && !sops.has(d.sop_number)) sops.set(d.sop_number, { ...d })
  const roots: SopRow[] = []
  for (const d of docs) {
    const own = d.kind === 'sop' && d.sop_number ? sops.get(d.sop_number) : undefined
    if (own && own.id === d.id) {
      roots.push(own)
      continue
    }
    const parent = d.parent_sop_number ? sops.get(d.parent_sop_number) : undefined
    if (parent) (parent.children ??= []).push({ ...d })
    else roots.push({ ...d })
  }
  return roots
}

export const STATUS_SOURCE_TEXT: Record<StatusSource, string> = {
  column: "Taken from the library's status column in SharePoint.",
  folder:
    'Taken from the SharePoint folder the document is filed in (e.g. Approved, Draft Unapproved, Superseded).',
  'content-approval': 'Taken from SharePoint content approval.',
  'version-number':
    'Inferred from the SharePoint version number (major versions are treated as published).',
  none: 'SharePoint holds no status information for this document.',
}
