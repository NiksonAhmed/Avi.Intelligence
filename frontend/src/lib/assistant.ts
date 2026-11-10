import type { AskResponse } from '../api/types'

export function sopLabel(item: { sop_number: string | null; title: string; version: string | null }): string {
  return `${item.sop_number ? `${item.sop_number} ` : ''}${item.title}${item.version ? ` v${item.version}` : ''}`
}

/** Plain-text version of a study answer for the clipboard. */
export function studyAnswerAsText(response: AskResponse): string {
  const a = response.study
  if (!a) return ''
  const tables = a.tables
    .map((t) => [t.title, t.columns.join(' | '), ...t.rows.map((r) => r.join(' | '))].join('\n'))
    .join('\n\n')
  return [a.headline, ...a.lines.map((l) => `- ${l}`), '', tables, '', a.note].join('\n').trim()
}

/** Plain-text version of an answer for the clipboard, keeping the numbered references. */
export function answerAsText(response: AskResponse): string {
  const body = response.segments
    .map((s) => s.text + s.citations.map((n) => ` [${n}]`).join(''))
    .join('')
  const sources = response.citations
    .map((c) => `[${c.number}] ${sopLabel(c)}, section: ${c.section}`)
    .join('\n')
  return `${body}\n\nSources:\n${sources}\n\nAI-generated from effective Avion SOPs. Verify against the source document.`
}
