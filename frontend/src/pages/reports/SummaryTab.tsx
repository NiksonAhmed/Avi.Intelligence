import { Alert, Button, Drawer, Empty, Flex, Skeleton, Typography } from 'antd'
import type { CSSProperties, ReactNode } from 'react'
import { useState } from 'react'

import { useReportSummary } from '../../api/hooks'
import type { ReportSummary, ReportTabKey, StudyStatus, SummaryCard } from '../../api/types'
import { formatDay } from '../../lib/format'
import { INK } from '../../lib/reports'
import { ReportToolbar, RuleInfo, Sparkline } from './ReportParts'

/**
 * The Reports summary (user decision 2026-11-16): what everyone sees first, with little text. Clicking a
 * card, ring or study opens a side panel with the few items behind the number, and from there the full
 * report. Every figure comes from the full reports.
 */

interface Props {
  studyId?: string
  onStudy: (id?: string) => void
  onOpenReport: (report: ReportTabKey, studyId?: string) => void
}

const CARD_STYLE: Record<string, { color: string; icon: string }> = {
  enrolment: { color: '#6A5AE0', icon: 'M16 21v-2a4 4 0 0 0-8 0v2M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z' },
  milestones: { color: '#C4502E', icon: 'M12 8v5l3 2M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z' },
  issues: { color: '#B7791F', icon: 'M12 9v4M12 17h.01M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z' },
  deviations: { color: '#1F6FD6', icon: 'M9 11l3 3 8-8M20 12v7a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h9' },
}
const RING_COLOR: Record<string, string> = { etmf: '#B7791F', enrolment: '#1A8F7A', sites: '#6A5AE0', ontime: '#1F6FD6' }
const SPARK_COLOR: Record<string, string> = { work: '#1F6FD6', issues: '#B7791F', etmf: '#C4502E' }
const SLICE_COLOR: Record<string, string> = { activated: '#1F6FD6', pending: '#1A8F7A', late: '#C4502E' }
const CHANGE_INK = { good: '#1A7F4B', bad: '#B42318', neutral: '#5B6B82' }
const STATUS = {
  off_track: { label: 'Off track', color: '#C4320A', bg: '#FDE4DC', fg: '#9A2A0A' },
  at_risk: { label: 'At risk', color: '#E0A21B', bg: '#FDF0D5', fg: '#7A4A06' },
  on_track: { label: 'On track', color: '#1A7F4B', bg: '#DCF5E7', fg: '#14633A' },
}

const panel: CSSProperties = { background: '#fff', border: '1px solid #DDE3EC', borderRadius: 14, padding: '18px 20px', minWidth: 0 }
const clickable: CSSProperties = { font: 'inherit', textAlign: 'left', cursor: 'pointer', color: 'inherit' }

function Section({ title, rule, children, style }: { title: string; rule?: string; children: ReactNode; style?: CSSProperties }) {
  return (
    <section aria-label={title} style={{ ...panel, display: 'flex', flexDirection: 'column', gap: 12, ...style }}>
      <Flex align="center" gap={6}>
        <Typography.Title level={2} style={{ margin: 0, fontSize: 16 }}>
          {title}
        </Typography.Title>
        {rule && <RuleInfo rule={rule} />}
      </Flex>
      {children}
    </section>
  )
}

function Card({ c, onOpen }: { c: SummaryCard; onOpen: () => void }) {
  const s = CARD_STYLE[c.key] ?? { color: INK.info, icon: '' }
  return (
    <button type="button" onClick={onOpen} aria-label={`${c.label}: ${c.value}. Show the detail`} data-testid={`summary-card-${c.key}`}
      style={{ ...panel, ...clickable, display: 'flex', flexDirection: 'column', gap: 14 }}>
      <Flex justify="space-between" align="flex-start" style={{ width: '100%' }}>
        <Flex vertical gap={4}>
          <span style={{ fontSize: 30, fontWeight: 700, lineHeight: 1, color: s.color }}>{c.value}</span>
          <span style={{ fontSize: 14, color: '#5B6B82' }}>{c.label}</span>
        </Flex>
        <span aria-hidden style={{ width: 48, height: 48, borderRadius: 24, background: s.color, color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d={s.icon} />
          </svg>
        </span>
      </Flex>
      <Flex justify="space-between" style={{ width: '100%', fontSize: 12, borderTop: '1px solid #EEF1F5', paddingTop: 10 }}>
        <span style={{ color: '#5B6B82' }}>{c.foot}</span>
        {c.change && <span style={{ fontWeight: 600, color: CHANGE_INK[c.change_tone] }}>{c.change}</span>}
      </Flex>
    </button>
  )
}

function StudyCard({ s, onOpen }: { s: StudyStatus; onOpen: () => void }) {
  const st = STATUS[s.status]
  return (
    <button type="button" onClick={onOpen} data-testid="summary-study" aria-label={`${s.protocol_number}: ${st.label}, ${s.reason}. Show the detail`}
      style={{ ...clickable, background: '#F7F9FC', border: '1px solid #DDE3EC', borderLeft: `5px solid ${st.color}`, borderRadius: 10, padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 6 }}>
      <Flex justify="space-between" align="center" gap={8} style={{ width: '100%' }}>
        <span style={{ fontWeight: 700 }}>{s.protocol_number}</span>
        <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 10, background: st.bg, color: st.fg }}>{st.label}</span>
      </Flex>
      <span style={{ fontSize: 12, color: '#5B6B82' }}>{s.what}</span>
      <Flex align="center" gap={8} style={{ width: '100%' }}>
        <div style={{ flex: 1, height: 6, borderRadius: 3, background: '#EDF0F5', overflow: 'hidden' }}>
          <div style={{ height: 6, width: `${Math.min(100, s.percent ?? 0)}%`, background: st.color }} />
        </div>
        <span style={{ fontSize: 12, color: '#5B6B82', whiteSpace: 'nowrap' }}>{s.target ? `${s.enrolled} of ${s.target}` : `${s.enrolled} enrolled`}</span>
      </Flex>
      <span style={{ fontSize: 12, fontWeight: 600, color: s.status === 'on_track' ? '#5B6B82' : st.fg }}>{s.reason}</span>
    </button>
  )
}

function monthLabel(m: string) {
  return new Date(`${m}-01T00:00:00`).toLocaleString('en-GB', { month: 'short' })
}

/** New patients each month (bars, own scale: the value is written on each) and the total (line) against the target. */
function EnrolmentChart({ data }: { data: ReportSummary }) {
  const months = data.enrolment
  if (months.length === 0) return <Empty description="No enrolment figures saved yet." />
  const target = data.enrolment_target
  const top = Math.max(1, target ?? 0, ...months.map((m) => m.total)) * 1.1
  const slot = 584 / months.length
  const y = (v: number) => 226 - (v / top) * 210
  const peak = Math.max(1, ...months.map((m) => m.new ?? 0))
  const pts = months.map((m, i) => ({ x: 44 + slot * i + slot / 2, y: y(m.total) }))
  return (
    <Flex vertical gap={8}>
      <svg viewBox="0 0 640 260" style={{ width: '100%', height: 'auto' }} role="img" data-testid="summary-enrolment"
        aria-label={`Total enrolled ${months.at(-1)?.total ?? 0}${target ? ` of a target of ${target}` : ''}.`}>
        {[0, 0.5, 1].map((f) => {
          const v = Math.round((top / 1.1) * f)
          return (
            <g key={f}>
              <line x1={44} x2={628} y1={y(v)} y2={y(v)} stroke="#EDF0F5" />
              <text x={36} y={y(v) + 4} fontSize="11" fill="#5B6B82" textAnchor="end">{v}</text>
            </g>
          )
        })}
        {months.map((m, i) => {
          const cx = 44 + slot * i + slot / 2
          const h = m.new ? (m.new / peak) * 70 : 0
          return (
            <g key={m.month}>
              {m.new !== null && h > 0 && <rect x={cx - slot * 0.28} y={226 - h} width={slot * 0.56} height={h} rx={4} fill="#1A8F7A" fillOpacity="0.8" />}
              {m.new !== null && <text x={cx} y={220 - h} fontSize="11" fontWeight="600" fill="#1A8F7A" textAnchor="middle">{m.new}</text>}
              <text x={cx} y={248} fontSize="11" fill="#5B6B82" textAnchor="middle">{monthLabel(m.month)}</text>
            </g>
          )
        })}
        {target !== null && (
          <>
            <line x1={44} x2={628} y1={y(target)} y2={y(target)} stroke="#8A97A8" strokeWidth="1.5" strokeDasharray="6 5" />
            <text x={628} y={y(target) - 6} fontSize="11" fill="#5B6B82" textAnchor="end">Target {target}</text>
          </>
        )}
        {pts.length > 1 && <polyline points={pts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')} fill="none" stroke="#6A5AE0" strokeWidth="3" strokeLinejoin="round" />}
        {pts.map((p, i) => <circle key={i} cx={p.x} cy={p.y} r={4.5} fill="#6A5AE0" stroke="#fff" strokeWidth="2" />)}
      </svg>
      <Flex gap={18} wrap style={{ fontSize: 12, color: '#5B6B82' }}>
        <Flex align="center" gap={6}><span style={{ width: 10, height: 10, borderRadius: 2, background: '#1A8F7A' }} />New that month</Flex>
        <Flex align="center" gap={6}><span style={{ width: 14, height: 3, borderRadius: 2, background: '#6A5AE0' }} />Total enrolled</Flex>
        {months.length < 2 && data.history_since && <span>The chart builds up month by month from {formatDay(data.history_since)}.</span>}
      </Flex>
    </Flex>
  )
}

function SitesDonut({ data, onOpen }: { data: ReportSummary; onOpen: () => void }) {
  const total = data.sites.reduce((n, s) => n + s.count, 0)
  const C = 2 * Math.PI * 74
  const shown = data.sites.filter((s) => s.count > 0)
  const arcs = shown.map((s, i) => ({
    ...s,
    len: total ? (s.count / total) * C : 0,
    start: shown.slice(0, i).reduce((n, x) => n + (total ? (x.count / total) * C : 0), 0),
  }))
  return (
    <button type="button" onClick={onOpen} aria-label={`${total} sites: ${data.sites.map((s) => `${s.count} ${s.label.toLowerCase()}`).join(', ')}. Show the detail`}
      style={{ ...clickable, border: 0, background: 'transparent', padding: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 }}>
      <svg viewBox="0 0 200 200" style={{ width: 180, height: 180 }} aria-hidden>
        <circle cx="100" cy="100" r="74" fill="none" stroke="#EDF0F5" strokeWidth="22" />
        {arcs.map((s) => (
          <circle key={s.key} cx="100" cy="100" r="74" fill="none" stroke={SLICE_COLOR[s.key]} strokeWidth="22"
            strokeDasharray={`${Math.max(0, s.len - 2)} ${C - s.len + 2}`} strokeDashoffset={-s.start} transform="rotate(-90 100 100)" />
        ))}
        <text x="100" y="98" fontSize="26" fontWeight="700" fill="#1F2937" textAnchor="middle">{total}</text>
        <text x="100" y="118" fontSize="12" fill="#5B6B82" textAnchor="middle">sites</text>
      </svg>
      <Flex gap={12} wrap justify="center" style={{ fontSize: 12, color: '#5B6B82' }}>
        {data.sites.map((s) => (
          <Flex key={s.key} align="center" gap={6}>
            <span style={{ width: 10, height: 10, borderRadius: 5, background: SLICE_COLOR[s.key] }} />
            {s.label} {s.count}
          </Flex>
        ))}
      </Flex>
    </button>
  )
}

function Ring({ percent, color, label }: { percent: number | null; color: string; label: string }) {
  const R = 2 * Math.PI * 46
  return (
    <svg viewBox="0 0 120 120" style={{ width: 120, height: 120 }} role="img" aria-label={`${label}: ${percent === null ? 'no figure yet' : `${percent}%`}`}>
      <circle cx="60" cy="60" r="46" fill="none" stroke="#EDF0F5" strokeWidth="9" />
      {percent !== null && <circle cx="60" cy="60" r="46" fill="none" stroke={color} strokeWidth="9" strokeLinecap="round" strokeDasharray={`${(Math.min(100, percent) / 100) * R} ${R}`} transform="rotate(-90 60 60)" />}
      <text x="60" y="67" fontSize="22" fontWeight="700" fill={percent === null ? '#5B6B82' : color} textAnchor="middle">{percent === null ? '—' : `${Math.round(percent)}%`}</text>
    </svg>
  )
}

export function SummaryTab({ studyId, onStudy, onOpenReport }: Props) {
  const { data, isLoading, isError, error, refetch } = useReportSummary(studyId)
  const [open, setOpen] = useState<string | null>(null)

  if (isError) {
    return (
      <Alert type="error" showIcon title="Could not load the summary" description={error.message}
        action={<Button onClick={() => void refetch()}>Try again</Button>} />
    )
  }
  if (isLoading || !data) return <Skeleton active paragraph={{ rows: 10 }} />

  const detail = open ? data.details[open] : undefined
  const show = (key: string) => () => setOpen(key)
  return (
    <Flex vertical gap={18}>
      <ReportToolbar
        filters={[
          {
            id: 'summary-study',
            label: 'Study',
            ariaLabel: 'Filter by study',
            placeholder: 'All studies',
            value: studyId,
            options: data.studies.map((s) => ({ id: s.id, label: s.protocol_number })),
            onChange: (id) => onStudy(id),
          },
        ]}
        source={data.source}
        about={data.rules.source}
        sync="simpletrials"
      />

      <section aria-label="Key figures" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 16 }}>
        {data.cards.map((c) => <Card key={c.key} c={c} onOpen={show(c.key)} />)}
      </section>

      <Section title="Studies at a glance" rule={data.rules.status}>
        {data.studies.length === 0 ? (
          <Empty description="No studies yet." />
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 12 }}>
            {data.studies.map((s) => <StudyCard key={s.id} s={s} onOpen={show(`study:${s.id}`)} />)}
          </div>
        )}
      </Section>

      <Flex gap={16} wrap>
        <Section title="Enrolment" rule={data.rules.enrolment} style={{ flex: '3 1 520px' }}>
          <EnrolmentChart data={data} />
        </Section>
        <Section title="Weekly trends" style={{ flex: '1 1 220px' }}>
          {data.sparks.map((s) => (
            <Flex key={s.key} vertical gap={2} data-testid="summary-spark">
              <span style={{ fontSize: 13, color: '#5B6B82' }}>{s.label}</span>
              <Flex justify="space-between" align="flex-end">
                <span style={{ fontSize: 20, fontWeight: 700 }}>{s.value}</span>
                <Sparkline points={s.points} color={SPARK_COLOR[s.key] ?? INK.info} />
              </Flex>
              {s.points.length < 2 && data.history_since && (
                <span style={{ fontSize: 11, color: '#5B6B82' }}>Trend builds up from {formatDay(data.history_since)}</span>
              )}
            </Flex>
          ))}
        </Section>
        <Section title="Sites" style={{ flex: '1 1 240px', alignItems: 'stretch' }}>
          <SitesDonut data={data} onOpen={show('sites')} />
        </Section>
      </Flex>

      <section aria-label="Progress" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 16 }}>
        {data.rings.map((r) => (
          <div key={r.key} data-testid={`summary-ring-${r.key}`} style={{ ...panel, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 }}>
            <Typography.Title level={2} style={{ margin: 0, fontSize: 15, alignSelf: 'flex-start' }}>{r.label}</Typography.Title>
            <Ring percent={r.percent} color={RING_COLOR[r.key] ?? INK.info} label={r.label} />
            <Button size="small" onClick={show(r.key)} style={{ borderColor: RING_COLOR[r.key], color: RING_COLOR[r.key] }}>
              View details
            </Button>
            <Flex justify="space-between" style={{ width: '100%', fontSize: 12, color: '#5B6B82' }}>
              <span>{r.left}</span>
              <span>{r.right}</span>
            </Flex>
          </div>
        ))}
      </section>

      <Drawer open={Boolean(detail)} onClose={() => setOpen(null)} title={detail?.title} size={420} destroyOnHidden>
        {detail && (
          <Flex vertical gap={16} style={{ height: '100%' }} data-testid="summary-detail">
            <Typography.Text type="secondary">{detail.summary}</Typography.Text>
            <Flex vertical>
              {detail.rows.length === 0 ? (
                <Typography.Text type="secondary">Nothing to list.</Typography.Text>
              ) : (
                detail.rows.map((r, i) => (
                  <Flex key={i} justify="space-between" gap={12} style={{ padding: '12px 0', borderBottom: '1px solid #EEF1F5' }}>
                    <span>{r.label}</span>
                    <span style={{ fontWeight: 600, whiteSpace: 'nowrap', color: r.tone === 'bad' ? INK.bad : r.tone === 'good' ? INK.good : undefined }}>{r.chip}</span>
                  </Flex>
                ))
              )}
            </Flex>
            <Button type="primary" size="large" style={{ marginTop: 'auto' }} onClick={() => { setOpen(null); onOpenReport(detail.report, detail.study_id ?? undefined) }}>
              Open the full report
            </Button>
            <Typography.Text type="secondary" style={{ fontSize: 12, textAlign: 'center' }}>
              The full report keeps every table, chart and rule.
            </Typography.Text>
          </Flex>
        )}
      </Drawer>
    </Flex>
  )
}
