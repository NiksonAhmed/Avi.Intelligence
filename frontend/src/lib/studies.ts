import type { MilestoneState, Risk, RiskStatus, ScheduleState, TaskStatus } from '../api/types'

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
  in_progress: { label: 'In progress', ...TONES.info },
  not_started: { label: 'Not started', ...TONES.neutral },
  upcoming: { label: 'Upcoming', ...TONES.info },
  not_planned: { label: 'No end date', ...TONES.neutral },
}

/** Rule key (from the API's `rules`) explaining each progress status. */
export const MILESTONE_STATE_RULE: Partial<Record<MilestoneState, string>> = {
  completed: 'milestone_completed',
  overdue: 'milestone_overdue',
  due_soon: 'milestone_due_soon',
  in_progress: 'milestone_in_progress',
  not_started: 'milestone_not_started',
}

export const SCHEDULE_STATE: Record<ScheduleState, ToneStyle & { rule: string }> = {
  on_plan: { label: 'On plan', ...TONES.good, rule: 'schedule_on_plan' },
  slipped: { label: 'Slipped', ...TONES.warn, rule: 'schedule_slipped' },
  slipped_major: { label: 'Slipped', ...TONES.bad, rule: 'schedule_slipped' },
  ahead: { label: 'Ahead', ...TONES.info, rule: 'schedule_ahead' },
  no_baseline: { label: 'No original date', ...TONES.neutral, rule: 'schedule_no_baseline' },
}

/** "+2 days" / "−8 days" for slipped or ahead; the plain label otherwise. */
export function scheduleLabel(state: ScheduleState, days: number | null): string {
  if ((state === 'slipped' || state === 'slipped_major') && days !== null) return `+${days} days`
  if (state === 'ahead' && days !== null) return `−${Math.abs(days)} days`
  return SCHEDULE_STATE[state].label
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
