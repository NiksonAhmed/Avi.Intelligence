/** Helpers for the Reports and Insights charts (pure, unit-tested). */

import type { DeliveryMilestone, ReportTone } from '../api/types'
import { TONES } from './studies'

const DAY = 24 * 60 * 60 * 1000
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

export function toUtc(day: string): number {
  return Date.parse(`${day}T00:00:00Z`)
}

export function todayIso(now = new Date()): string {
  return now.toISOString().slice(0, 10)
}

export interface Range {
  start: number
  end: number
}

/** Timeline range: every original and current date plus today, padded to whole months. */
export function timelineRange(rows: DeliveryMilestone[], today: string): Range {
  const days = [today, ...rows.flatMap((r) => [r.original_date, r.current_date])].filter(
    (d): d is string => Boolean(d),
  )
  const times = days.map(toUtc)
  const min = new Date(Math.min(...times))
  const max = new Date(Math.max(...times))
  const start = Date.UTC(min.getUTCFullYear(), min.getUTCMonth(), 1)
  const end = Date.UTC(max.getUTCFullYear(), max.getUTCMonth() + 1, 1)
  return { start, end: Math.max(end, start + 31 * DAY) }
}

/** Position of a day within the range, as a percentage (0–100). */
export function positionPct(day: string, range: Range): number {
  const pct = ((toUtc(day) - range.start) / (range.end - range.start)) * 100
  return Math.min(100, Math.max(0, pct))
}

/** Month ticks for the axis: at most `maxTicks`, evenly spaced in whole months. */
export function axisTicks(range: Range, maxTicks = 8): { label: string; pct: number }[] {
  const first = new Date(range.start)
  const months =
    (new Date(range.end).getUTCFullYear() - first.getUTCFullYear()) * 12 +
    new Date(range.end).getUTCMonth() -
    first.getUTCMonth()
  const step = Math.max(1, Math.ceil(months / maxTicks))
  const ticks = []
  for (let m = 0; m < months; m += step) {
    const t = Date.UTC(first.getUTCFullYear(), first.getUTCMonth() + m, 1)
    const d = new Date(t)
    ticks.push({
      label: `${MONTHS[d.getUTCMonth()]} ${String(d.getUTCFullYear()).slice(2)}`,
      pct: ((t - range.start) / (range.end - range.start)) * 100,
    })
  }
  return ticks
}

/** Strong colour (bars, dots, big numbers) for each tone; text-safe on white. */
export const INK: Record<ReportTone, string> = {
  good: '#1E7F4F',
  info: '#1F4E8C',
  warn: '#B26B00',
  bad: '#B42318',
  neutral: '#0A1F3C',
}

export function toneStyle(tone: ReportTone, label: string) {
  return { label, ...TONES[tone] }
}

/** The tone of a key milestone on the timeline (its dot and status label). */
export function milestoneTone(m: DeliveryMilestone): { tone: ReportTone; label: string } {
  const slip = m.variance_days
  if (m.state === 'completed') {
    if (m.on_time === false && slip) return { tone: 'warn', label: `Completed +${slip}d` }
    return { tone: 'good', label: 'Completed' }
  }
  if (m.state === 'overdue') return { tone: 'bad', label: slip ? `Overdue +${slip}d` : 'Overdue' }
  if (m.schedule === 'slipped_major') return { tone: 'bad', label: `Slipped +${slip}d` }
  if (m.schedule === 'slipped') return { tone: 'warn', label: `Slipped +${slip}d` }
  if (m.schedule === 'ahead' && slip) return { tone: 'info', label: `Ahead −${Math.abs(slip)}d` }
  if (m.state === 'due_soon') return { tone: 'warn', label: 'Due soon' }
  if (m.schedule === 'no_baseline') return { tone: 'neutral', label: 'No original date' }
  return { tone: 'info', label: 'On plan' }
}
