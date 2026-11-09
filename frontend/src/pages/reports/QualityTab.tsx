import { Alert, Button, Empty, Flex, Skeleton, Table, Typography } from 'antd'
import type { HTMLAttributes } from 'react'
import { Link } from 'react-router'

import { reportExportUrl } from '../../api/client'
import { useQualityReport } from '../../api/hooks'
import type { QualityChange, QualityMonth, QualityReport, QualityReportFilters, QualityScheduleRow, ReportTone, ReviewState } from '../../api/types'
import { ToneTag } from '../../components/ToneTag'
import { formatDateTime, formatDay } from '../../lib/format'
import { CHANGE_PERIODS as PERIODS, INK, todayIso, toneStyle } from '../../lib/reports'
import { ChartCard, ReportTiles, ReportToolbar } from './ReportParts'

interface Props {
  filters: QualityReportFilters
  onFilters: (next: QualityReportFilters) => void
}


const REVIEW: Record<ReviewState, { tone: ReportTone; label: (r: QualityScheduleRow) => string }> = {
  overdue: { tone: 'bad', label: (r) => `Overdue ${Math.abs(r.days_to_review ?? 0)}d` },
  due_soon: { tone: 'warn', label: (r) => (r.days_to_review === 0 ? 'Due today' : `Due in ${r.days_to_review}d`) },
  scheduled: { tone: 'good', label: () => 'Scheduled' },
  no_date: { tone: 'neutral', label: () => 'No review date' },
}

function sopLink(id: string, text: string) {
  return <Link to={`/documents/sops/${encodeURIComponent(id)}`}>{text}</Link>
}

/** Column chart: overdue reviews, then each of the next 12 months. */
export function ReviewsByMonth({ months, later }: { months: QualityMonth[]; later: number }) {
  const max = Math.max(1, ...months.map((m) => m.count))
  const HEIGHT = 120
  return (
    <Flex vertical gap={8}>
      <div style={{ overflowX: 'auto' }}>
        <Flex gap={6} align="flex-end" style={{ minWidth: 560, height: HEIGHT + 44 }}>
          {months.map((m) => {
            const color = m.key === 'overdue' ? INK.bad : INK.info
            const label = `${m.label}: ${m.count} review${m.count === 1 ? '' : 's'}${m.items.length ? ` (${m.items.join(', ')})` : ''}`
            return (
              <Flex key={m.key} vertical align="center" gap={4} style={{ flex: '1 1 0' }} data-testid="review-month" title={label}>
                <span style={{ fontSize: 12, fontWeight: 700, color: m.count ? color : '#8A97A8' }}>{m.count}</span>
                <div
                  role="img"
                  aria-label={label}
                  style={{
                    width: '70%',
                    height: m.count ? Math.max(4, (m.count / max) * HEIGHT) : 2,
                    background: m.count ? color : '#EEF1F5',
                    borderRadius: '3px 3px 0 0',
                  }}
                />
                <span style={{ fontSize: 11, color: m.key === 'overdue' ? INK.bad : '#5B6B82', fontWeight: m.key === 'overdue' ? 700 : 400, whiteSpace: 'nowrap' }}>
                  {m.label}
                </span>
              </Flex>
            )
          })}
        </Flex>
      </div>
      {later > 0 && (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {later} more review{later === 1 ? '' : 's'} due after these 12 months.
        </Typography.Text>
      )}
    </Flex>
  )
}

function ReviewSchedule({ rows }: { rows: QualityScheduleRow[] }) {
  return (
    <Table<QualityScheduleRow>
      size="small"
      rowKey="id"
      pagination={rows.length > 15 ? { pageSize: 15, showSizeChanger: false } : false}
      dataSource={rows}
      scroll={{ x: 760 }}
      locale={{ emptyText: <Empty description="No approved SOPs in this selection." /> }}
      onRow={() => ({ 'data-testid': 'schedule-row' }) as HTMLAttributes<HTMLElement>}
      columns={[
        {
          title: 'SOP',
          key: 'sop',
          render: (_, r) => (
            <Flex vertical>
              {sopLink(r.id, r.sop_number ? `${r.sop_number} · ${r.title}` : r.title)}
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {[r.version && `v${r.version}`, r.department, r.forms ? `${r.forms} form${r.forms === 1 ? '' : 's'}` : null]
                  .filter(Boolean)
                  .join(' · ')}
              </Typography.Text>
            </Flex>
          ),
        },
        { title: 'Owner', dataIndex: 'owner', render: (v: string | null) => v ?? '—' },
        { title: 'Effective', dataIndex: 'effective_date', render: (v: string | null) => formatDay(v) },
        { title: 'Next review', dataIndex: 'review_date', render: (v: string | null) => formatDay(v) },
        {
          title: 'Review',
          key: 'state',
          render: (_, r) => <ToneTag tone={toneStyle(REVIEW[r.state].tone, REVIEW[r.state].label(r))} />,
        },
        {
          title: 'Open review tasks',
          dataIndex: 'open_tasks',
          align: 'right',
          render: (v: number) => (v ? <strong>{v}</strong> : <Typography.Text type="secondary">0</Typography.Text>),
        },
      ]}
    />
  )
}

function LibraryHealth({ report }: { report: QualityReport }) {
  const checks = [...report.health].sort((a, b) => Number(b.count > 0) - Number(a.count > 0))
  return (
    <Flex vertical>
      {checks.map((c) => (
        <Flex key={c.key} vertical gap={4} data-testid={`health-${c.key}`} style={{ padding: '10px 0', borderTop: '1px solid #EEF1F5' }}>
          <Flex justify="space-between" align="center" gap={8}>
            <Flex vertical style={{ minWidth: 0 }}>
              <span style={{ fontWeight: 600 }}>{c.label}</span>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {c.description}
              </Typography.Text>
            </Flex>
            <ToneTag tone={c.count ? toneStyle('warn', String(c.count)) : toneStyle('good', 'None')} />
          </Flex>
          {c.items.length > 0 && (
            <Flex gap={4} wrap style={{ fontSize: 13 }}>
              {c.items.slice(0, 12).map((i, n) => (
                <span key={i.id}>
                  {sopLink(i.id, i.label)}
                  {n < Math.min(c.items.length, 12) - 1 ? ',' : ''}
                </span>
              ))}
              {c.items.length > 12 && <Typography.Text type="secondary">and {c.items.length - 12} more</Typography.Text>}
            </Flex>
          )}
        </Flex>
      ))}
    </Flex>
  )
}

function ChangeLog({ changes, months }: { changes: QualityChange[]; months: number }) {
  if (changes.length === 0) {
    return <Typography.Text type="secondary">No changes in the last {months} months.</Typography.Text>
  }
  return (
    <Flex vertical>
      {changes.map((c) => (
        <Flex
          key={`${c.id}-${c.version}-${c.issued}`}
          gap={14}
          data-testid="change-row"
          style={{ padding: '8px 0', borderTop: '1px solid #EEF1F5' }}
        >
          <span style={{ width: 96, flexShrink: 0, fontSize: 13, fontWeight: 600 }}>{formatDay(c.issued)}</span>
          <Flex vertical style={{ minWidth: 0 }}>
            <span>
              {sopLink(c.id, c.sop_number ? `${c.sop_number} · ${c.title}` : c.title)}{' '}
              <Typography.Text type="secondary">v{c.version}</Typography.Text>
            </span>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {c.changes ?? 'Current version took effect (no readable change history)'}
            </Typography.Text>
          </Flex>
        </Flex>
      ))}
    </Flex>
  )
}

export function QualityTab({ filters, onFilters }: Props) {
  const { data, isLoading, isError, error, refetch } = useQualityReport(filters)

  if (isError) {
    return (
      <Alert
        type="error"
        showIcon
        title="Could not load the Quality (SOPs) report"
        description={error.message}
        action={<Button onClick={() => void refetch()}>Try again</Button>}
      />
    )
  }
  if (isLoading || !data) return <Skeleton active paragraph={{ rows: 10 }} />

  const live = data.source.mode === 'live'
  return (
    <Flex vertical gap={18}>
      <ReportToolbar
        filters={[
          {
            id: 'report-department',
            label: 'Department',
            ariaLabel: 'Filter by department',
            placeholder: 'All departments',
            value: filters.department,
            options: data.department_options,
            onChange: (d) => onFilters({ ...filters, department: d }),
            width: 240,
          },
          {
            id: 'report-period',
            label: 'Change log period',
            ariaLabel: 'Change log period',
            placeholder: 'Last 12 months',
            value: filters.months ? String(filters.months) : undefined,
            options: PERIODS.map((m) => ({ id: String(m), label: `Last ${m} months` })),
            onChange: (m) => onFilters({ ...filters, months: m ? Number(m) : undefined }),
            width: 180,
          },
        ]}
        sourceText={`As of ${formatDateTime(data.fetched_at)} · ${live ? 'Source: SharePoint SOP library (approved documents)' : 'Source: demo data'}`}
        excelUrl={reportExportUrl('quality', {
          department: filters.department,
          months: filters.months ? String(filters.months) : undefined,
        })}
      />
      <div className="print-only">
        <Typography.Title level={2} style={{ margin: 0 }}>
          Quality (SOPs) report
        </Typography.Title>
        <Typography.Text type="secondary">
          {filters.department ?? 'All departments'} · {formatDay(todayIso())}
        </Typography.Text>
      </div>
      {!live && <Alert type="warning" showIcon title="Demo data: SharePoint is not connected" />}

      <ReportTiles tiles={data.tiles} />

      <ChartCard title="Reviews due by month" rule={data.rules.review}>
        <ReviewsByMonth months={data.by_month} later={data.later} />
      </ChartCard>

      <ChartCard title="Review schedule" rule={data.rules.tasks}>
        <ReviewSchedule rows={data.schedule} />
      </ChartCard>

      <Flex gap={18} wrap>
        <ChartCard title="Library health" rule={data.rules.health} flex="1 1 460px">
          <LibraryHealth report={data} />
        </ChartCard>
        <ChartCard title={`Change log · last ${data.months} months`} rule={data.rules.change_log} flex="1 1 460px">
          <ChangeLog changes={data.changes} months={data.months} />
        </ChartCard>
      </Flex>
    </Flex>
  )
}
