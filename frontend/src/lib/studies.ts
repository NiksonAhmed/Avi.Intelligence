import type { MilestoneState, Risk, RiskStatus, TaskStatus } from '../api/types'

/** Labels and accessible colours (text ≥ 4.5:1 on its background) for derived states. */
export interface ToneStyle {
  label: string
  color: string
  background: string
  border: string
}

const TONES = {
  good: { color: '#0F5B36', background: '#E6F4EC', border: '#9CD1B4' },
  info: { color: '#1A4475', background: '#E8F0FB', border: '#A9C4EA' },
  warn: { color: '#7A4A00', background: '#FDF3E1', border: '#EDC98A' },
  bad: { color: '#8A1C12', background: '#FDECEA', border: '#F1B0A8' },
  neutral: { color: '#3E4C5E', background: '#EEF1F5', border: '#C9D1DC' },
}

export const MILESTONE_STATE: Record<MilestoneState, ToneStyle> = {
  completed: { label: 'Completed', ...TONES.good },
  overdue: { label: 'Overdue', ...TONES.bad },
  due_soon: { label: 'Due soon', ...TONES.warn },
  upcoming: { label: 'Upcoming', ...TONES.info },
  not_planned: { label: 'No planned date', ...TONES.neutral },
}

export const TASK_STATUS_STYLE: Record<TaskStatus, ToneStyle> = {
  'Not started': { label: 'Not started', ...TONES.neutral },
  'In progress': { label: 'In progress', ...TONES.info },
  Blocked: { label: 'Blocked', ...TONES.bad },
  Completed: { label: 'Completed', ...TONES.good },
  Cancelled: { label: 'Cancelled', ...TONES.neutral },
}

export const RISK_STATUS_STYLE: Record<RiskStatus, ToneStyle> = {
  Open: { label: 'Open', ...TONES.warn },
  Mitigating: { label: 'Mitigating', ...TONES.info },
  Closed: { label: 'Closed', ...TONES.neutral },
}

export const RISK_RATING_STYLE: Record<Risk['rating'], ToneStyle> = {
  High: { label: 'High', ...TONES.bad },
  Medium: { label: 'Medium', ...TONES.warn },
  Low: { label: 'Low', ...TONES.good },
}

export const LEVELS: Record<number, string> = { 1: 'Low', 2: 'Medium', 3: 'High' }

/** "31 of 120 (25.8%)", or a plain statement of what is missing. Never estimates. */
export function enrolmentText(enrolled: number | null, target: number | null, pct: number | null): string {
  if (enrolled === null) return 'Not reported'
  if (pct === null || !target) return `${enrolled} enrolled · no target recorded`
  return `${enrolled} of ${target} (${pct}%)`
}

/** Tasks a person should look at first: overdue, then due within 7 days, then the rest. */
export function taskBucket(due: string | null, overdue: boolean, today = new Date()): 'overdue' | 'week' | 'later' {
  if (overdue) return 'overdue'
  if (!due) return 'later'
  const dueMs = Date.parse(`${due}T00:00:00Z`)
  const todayMs = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate())
  return dueMs - todayMs <= 7 * 86_400_000 ? 'week' : 'later'
}
