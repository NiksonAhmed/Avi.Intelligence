import { Alert, Button, Empty, Flex, Skeleton, Typography } from 'antd'

import { reportExportUrl } from '../../api/client'
import { useStudyDelivery } from '../../api/hooks'
import type { DeliveryMilestone, DeliverySite, PendingSite, ReportFilters, StudyDeliveryReport } from '../../api/types'
import { ToneTag } from '../../components/ToneTag'
import { formatDay, formatDayShort } from '../../lib/format'
import { INK, axisTicks, milestoneTone, positionPct, timelineRange, todayIso, toneStyle } from '../../lib/reports'
import { Bar, ChartCard, ReportTiles, ReportToolbar } from './ReportParts'

interface Props {
  filters: ReportFilters
  onFilters: (next: ReportFilters) => void
}

const LABEL_W = 240
const STATUS_W = 130

function MilestoneTimeline({ rows, today }: { rows: DeliveryMilestone[]; today: string }) {
  if (rows.length === 0) return <Empty description="No key milestones in SimpleTrials for this selection." />
  const range = timelineRange(rows, today)
  const ticks = axisTicks(range)
  const todayLeft = positionPct(today, range)
  return (
    <div style={{ overflowX: 'auto' }}>
      <div style={{ minWidth: 760 }}>
        <Flex gap={12}>
          <div style={{ width: LABEL_W, flexShrink: 0 }} />
          <div style={{ position: 'relative', flex: '1 1 auto', height: 20 }} aria-hidden>
            {ticks.map((t) => (
              <span key={t.label} style={{ position: 'absolute', left: `${t.pct}%`, fontSize: 11, color: '#5B6B82', whiteSpace: 'nowrap' }}>
                {t.label}
              </span>
            ))}
          </div>
          <div style={{ width: STATUS_W, flexShrink: 0 }} />
        </Flex>
        {rows.map((m) => {
          const { tone, label } = milestoneTone(m)
          const color = INK[tone]
          const orig = m.original_date ? positionPct(m.original_date, range) : null
          const cur = m.current_date ? positionPct(m.current_date, range) : null
          const lo = orig !== null && cur !== null ? Math.min(orig, cur) : null
          const hi = orig !== null && cur !== null ? Math.max(orig, cur) : null
          const tip =
            `${m.name} · ${m.protocol_number}: original ${formatDay(m.original_date)}, current ${formatDay(m.current_date)}` +
            (m.completed_on ? `, completed ${formatDay(m.completed_on)}` : '') +
            (m.completion_basis === 'before-tracking' ? ' (completed before tracking began)' : '')
          return (
            <Flex
              key={`${m.study_id}-${m.name}-${m.current_date}`}
              gap={12}
              align="center"
              title={tip}
              data-testid="timeline-row"
              style={{ minHeight: 42, borderTop: '1px solid #EEF1F5' }}
            >
              <Flex vertical style={{ width: LABEL_W, flexShrink: 0 }}>
                <span style={{ fontWeight: 600 }}>{m.name}</span>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {m.protocol_number} · {formatDayShort(m.current_date)}
                </Typography.Text>
              </Flex>
              <div style={{ position: 'relative', flex: '1 1 auto', height: 24 }} role="img" aria-label={tip}>
                <div style={{ position: 'absolute', left: 0, right: 0, top: 11, height: 2, background: '#EEF1F5' }} />
                <div style={{ position: 'absolute', top: -4, bottom: -4, width: 2, background: '#B42318', left: `${todayLeft}%` }} />
                {lo !== null && hi !== null && hi > lo && (
                  <div style={{ position: 'absolute', top: 10, height: 4, borderRadius: 2, background: color, opacity: 0.35, left: `${lo}%`, width: `${hi - lo}%` }} />
                )}
                {orig !== null && (
                  <div style={{ position: 'absolute', top: 5, width: 14, height: 14, marginLeft: -7, borderRadius: '50%', border: '2px solid #8A97A8', background: '#FFFFFF', boxSizing: 'border-box', left: `${orig}%` }} />
                )}
                {cur !== null && (
                  <div style={{ position: 'absolute', top: 5, width: 14, height: 14, marginLeft: -7, borderRadius: '50%', background: color, left: `${cur}%` }} />
                )}
              </div>
              <div style={{ width: STATUS_W, flexShrink: 0, textAlign: 'right' }}>
                <ToneTag tone={toneStyle(tone, label)} />
              </div>
            </Flex>
          )
        })}
      </div>
    </div>
  )
}

function siteFigure(s: DeliverySite): { text: string; tone: 'good' | 'warn' | 'bad' | 'neutral' } {
  if (s.flag === 'no_target') return { text: `${s.enrolled ?? 0} enrolled · no target recorded`, tone: 'neutral' }
  const pct = s.percent ?? 0
  return {
    text: `${s.enrolled ?? 0} of ${s.target} (${pct}%)`,
    tone: s.flag === 'zero' ? 'bad' : pct < 50 ? 'warn' : 'good',
  }
}

function EnrolmentBySite({ sites }: { sites: DeliverySite[] }) {
  if (sites.length === 0) return <Empty description="No sites for this selection." />
  return (
    <Flex vertical gap={12}>
      {sites.map((s) => {
        const f = siteFigure(s)
        const label = `${s.site_number} · ${s.name} (${s.protocol_number}): ${f.text}`
        return (
          <Flex key={s.site_id} vertical gap={6} data-testid="enrolment-row">
            <Flex justify="space-between" gap={8}>
              <span style={{ fontWeight: 600 }}>
                {s.site_number} · {s.name}{' '}
                <Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 400 }}>
                  {s.protocol_number}
                </Typography.Text>
              </span>
              <span style={{ fontSize: 13, fontWeight: 700, color: f.tone === 'neutral' ? '#5B6B82' : toneStyle(f.tone, '').color, whiteSpace: 'nowrap' }}>
                {f.text}
              </span>
            </Flex>
            {s.flag !== 'no_target' && <Bar percent={s.percent ?? 0} color={INK[f.tone]} label={label} />}
          </Flex>
        )
      })}
    </Flex>
  )
}

const PENDING: Record<PendingSite['state'], { tone: 'bad' | 'warn' | 'info' | 'neutral'; label: (p: PendingSite) => string }> = {
  late: { tone: 'bad', label: (p) => `${p.days_late} days late` },
  due_soon: { tone: 'warn', label: () => 'Due soon' },
  upcoming: { tone: 'info', label: () => 'Upcoming' },
  no_date: { tone: 'neutral', label: () => 'No planned date' },
}

function SiteActivation({ report }: { report: StudyDeliveryReport }) {
  const a = report.activation
  return (
    <Flex vertical gap={12}>
      <Flex align="baseline" gap={8} wrap>
        <span data-testid="activation-figure" style={{ fontSize: 28, fontWeight: 700 }}>
          {a.activated} of {a.total}
        </span>
        <Typography.Text type="secondary">sites activated{a.percent !== null ? ` (${a.percent}%)` : ''}</Typography.Text>
      </Flex>
      <Bar percent={a.percent ?? 0} color={INK.info} height={12} label={`${a.activated} of ${a.total} sites activated`} />
      {a.with_target > 0 && (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {a.on_time} of {a.with_target} activated on or before the planned date
        </Typography.Text>
      )}
      <Typography.Title level={3} style={{ margin: '6px 0 0', fontSize: 14 }}>
        Not yet activated
      </Typography.Title>
      {report.pending_sites.length === 0 ? (
        <Typography.Text type="secondary">All sites in this selection are activated.</Typography.Text>
      ) : (
        report.pending_sites.map((p) => {
          const s = PENDING[p.state]
          return (
            <Flex key={p.site_id} justify="space-between" align="center" gap={8} style={{ padding: '8px 0', borderTop: '1px solid #EEF1F5' }}>
              <Flex vertical style={{ minWidth: 0 }}>
                <span style={{ fontWeight: 600 }}>
                  {p.site_number} · {p.name}
                </span>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {p.protocol_number}
                  {p.status ? ` · ${p.status}` : ''} · {p.planned_date ? `Planned ${formatDay(p.planned_date)}` : 'No planned date'}
                </Typography.Text>
              </Flex>
              <ToneTag tone={toneStyle(s.tone, s.label(p))} />
            </Flex>
          )
        })
      )}
    </Flex>
  )
}

export function StudyDeliveryTab({ filters, onFilters }: Props) {
  const { data, isLoading, isError, error, refetch } = useStudyDelivery(filters)

  if (isError) {
    return (
      <Alert
        type="error"
        showIcon
        title="Could not load the Study delivery report"
        description={error.message}
        action={<Button onClick={() => void refetch()}>Try again</Button>}
      />
    )
  }
  if (isLoading || !data) return <Skeleton active paragraph={{ rows: 10 }} />

  const today = todayIso()
  const ot = data.on_time
  return (
    <Flex vertical gap={18}>
      <ReportToolbar
        filters={[
          {
            id: 'report-study',
            label: 'Study',
            ariaLabel: 'Filter by study',
            placeholder: 'All studies',
            value: filters.study_id,
            options: data.study_options,
            onChange: (id) => onFilters({ study_id: id, site_id: undefined }),
            width: 300,
          },
          {
            id: 'report-site',
            label: 'Site',
            ariaLabel: 'Filter by site',
            placeholder: 'All sites',
            value: filters.site_id,
            options: data.site_options,
            onChange: (id) => onFilters({ ...filters, site_id: id }),
            width: 260,
          },
        ]}
        source={data.source}
        excelUrl={reportExportUrl('study-delivery', { study_id: filters.study_id, site_id: filters.site_id })}
      />
      <div className="print-only">
        <Typography.Title level={2} style={{ margin: 0 }}>
          Study delivery report
        </Typography.Title>
        <Typography.Text type="secondary">
          {data.study_options.find((o) => o.id === filters.study_id)?.label ?? 'All studies'} · as of{' '}
          {data.source.as_of ? formatDay(data.source.as_of.slice(0, 10)) : '—'}
        </Typography.Text>
      </div>
      {data.source.mode !== 'api' && (
        <Alert type="warning" showIcon title="Demo data: SimpleTrials is not connected" />
      )}
      {data.source.mode === 'api' && data.source.sandbox_only && (
        <Alert
          type="info"
          showIcon
          title="SimpleTrials sandbox study"
          description="Figures come from the sandbox study only. All studies appear once the Workspace (all studies) read-only key is enabled."
        />
      )}

      <ReportTiles tiles={data.tiles} />

      <ChartCard
        title="Key milestone timeline"
        rule={`${data.rules.schedule_slipped ?? ''} ${data.rules.study_on_plan ?? ''}`.trim()}
        extra={
          <Flex gap={14} wrap style={{ fontSize: 12, color: '#3E4C5E' }} aria-hidden>
            <Flex align="center" gap={6}>
              <span style={{ width: 12, height: 12, borderRadius: '50%', border: '2px solid #8A97A8', boxSizing: 'border-box' }} />
              Original date
            </Flex>
            <Flex align="center" gap={6}>
              <span style={{ width: 12, height: 12, borderRadius: '50%', background: INK.info }} />
              Current date
            </Flex>
            <Flex align="center" gap={6}>
              <span style={{ width: 2, height: 14, background: '#B42318' }} />
              Today
            </Flex>
          </Flex>
        }
      >
        <MilestoneTimeline rows={data.milestones} today={today} />
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {ot.with_original_date > 0
            ? `${ot.on_time} of ${ot.with_original_date} completed key milestones were on time. `
            : 'On-time completion appears as milestones are completed. '}
          {data.rules.on_time}
          {data.source.snapshot_days < 14 &&
            ` Trend charts (slippage over time) appear after two weeks of daily history (${data.source.snapshot_days} day${data.source.snapshot_days === 1 ? '' : 's'} so far).`}
        </Typography.Text>
      </ChartCard>

      <Flex gap={18} wrap>
        <ChartCard title="Enrolment by site" rule={data.rules.enrolment} flex="1 1 520px">
          <EnrolmentBySite sites={data.sites} />
        </ChartCard>
        <ChartCard title="Site activation" rule={data.rules.activation} flex="1 1 380px">
          <SiteActivation report={data} />
        </ChartCard>
      </Flex>
    </Flex>
  )
}
