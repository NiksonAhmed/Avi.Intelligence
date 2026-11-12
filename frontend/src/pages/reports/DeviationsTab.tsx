import { Alert, Button, Flex, Skeleton, Table, Tag, Typography } from 'antd'
import type { HTMLAttributes } from 'react'

import { reportExportUrl } from '../../api/client'
import { useDeviationsReport } from '../../api/hooks'
import type { DeviationCount, DeviationRow, DeviationsReport, ReportFilters } from '../../api/types'
import { formatDay } from '../../lib/format'
import { INK, todayIso } from '../../lib/reports'
import { Bar, ChartCard, Legend, ReportTiles, ReportToolbar, StackedBar } from './ReportParts'

interface Props {
  filters: ReportFilters
  onFilters: (next: ReportFilters) => void
}

const SEVERITY_COLOUR: Record<string, string> = { Critical: INK.bad, Major: INK.warn, Minor: INK.info }
const OTHER_COLOUR = '#8A97A8'
const SEVERITY_TAG: Record<string, string> = { Critical: 'red', Major: 'orange', Minor: 'blue' }
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function monthLabel(ym: string): string {
  const [y, m] = ym.split('-')
  return `${MONTHS[Number(m) - 1] ?? m} ${y?.slice(2)}`
}

/** Horizontal bars: total, with the open share darker. */
function Counts({ rows, colourFor, testId, empty }: { rows: DeviationCount[]; colourFor: (label: string) => string; testId: string; empty: string }) {
  if (rows.length === 0) return <Typography.Text type="secondary">{empty}</Typography.Text>
  const max = Math.max(1, ...rows.map((r) => r.count))
  return (
    <Flex vertical gap={10}>
      {rows.map((r) => (
        <Flex key={r.key} gap={12} align="center" data-testid={testId}>
          <span style={{ width: 170, flexShrink: 0, fontSize: 13 }}>{r.label}</span>
          <div style={{ flex: '1 1 auto', minWidth: 60 }}>
            <StackedBar
              max={max}
              label={`${r.label}: ${r.count} (${r.open} open)`}
              segments={[
                { value: r.open, color: colourFor(r.label) },
                { value: r.count - r.open, color: `${colourFor(r.label)}66` },
              ]}
            />
          </div>
          <span style={{ width: 90, textAlign: 'right', fontSize: 13 }}>
            <strong>{r.count}</strong> <Typography.Text type="secondary">({r.open} open)</Typography.Text>
          </span>
        </Flex>
      ))}
    </Flex>
  )
}

/** Monthly columns stacked by severity. */
function Trend({ report }: { report: DeviationsReport }) {
  const max = Math.max(1, ...report.trend.map((m) => m.critical + m.major + m.minor + m.other))
  return (
    <Flex vertical gap={8}>
      <Flex align="flex-end" gap={6} style={{ height: 150 }} role="img" aria-label="Deviations by month and severity">
        {report.trend.map((m) => {
          const total = m.critical + m.major + m.minor + m.other
          const parts = [
            { v: m.critical, c: SEVERITY_COLOUR.Critical },
            { v: m.major, c: SEVERITY_COLOUR.Major },
            { v: m.minor, c: SEVERITY_COLOUR.Minor },
            { v: m.other, c: OTHER_COLOUR },
          ]
          return (
            <Flex
              key={m.month}
              vertical
              justify="flex-end"
              data-testid="deviation-month"
              title={`${monthLabel(m.month)}: ${total} (critical ${m.critical}, major ${m.major}, minor ${m.minor}${m.other ? `, other ${m.other}` : ''})`}
              style={{ flex: '1 1 0', height: '100%', minWidth: 14 }}
            >
              {total > 0 && (
                <span style={{ fontSize: 11, textAlign: 'center', color: '#3E4C5E' }}>{total}</span>
              )}
              <Flex vertical style={{ height: `${(total / max) * 120}px`, borderRadius: 3, overflow: 'hidden' }}>
                {parts.filter((p) => p.v > 0).map((p, i) => (
                  <div key={i} style={{ flex: p.v, background: p.c }} />
                ))}
              </Flex>
            </Flex>
          )
        })}
      </Flex>
      <Flex gap={6}>
        {report.trend.map((m) => (
          <span key={m.month} style={{ flex: '1 1 0', minWidth: 14, fontSize: 10, color: '#5B6B82', textAlign: 'center' }}>
            {monthLabel(m.month)}
          </span>
        ))}
      </Flex>
      <Legend
        items={[
          { label: 'Critical', color: SEVERITY_COLOUR.Critical! },
          { label: 'Major', color: SEVERITY_COLOUR.Major! },
          { label: 'Minor', color: SEVERITY_COLOUR.Minor! },
          { label: 'Other / not classified', color: OTHER_COLOUR },
        ]}
      />
    </Flex>
  )
}

function Sites({ report }: { report: DeviationsReport }) {
  if (report.by_site.length === 0) return <Typography.Text type="secondary">No site deviations in this selection.</Typography.Text>
  const max = Math.max(1, ...report.by_site.map((s) => s.per_10 ?? 0))
  return (
    <Flex vertical gap={12}>
      {report.by_site.map((s) => (
        <Flex key={s.key} vertical gap={4} data-testid="deviation-site-row">
          <Flex justify="space-between" gap={8} wrap>
            <span style={{ fontWeight: 600 }}>
              {s.label} <Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 400 }}>{s.protocol_number}</Typography.Text>
            </span>
            <span style={{ fontSize: 13 }}>
              <strong>{s.total}</strong> ({s.open} open, {s.major} major/critical) ·{' '}
              {s.per_10 !== null ? <strong>{s.per_10} per 10 enrolled</strong> : <Typography.Text type="secondary">no enrolled subjects</Typography.Text>}
            </span>
          </Flex>
          <Bar percent={((s.per_10 ?? 0) / max) * 100} color={s.major ? INK.warn : INK.info} label={`${s.label}: ${s.per_10 ?? 'no'} deviations per 10 enrolled subjects`} />
        </Flex>
      ))}
    </Flex>
  )
}

export function DeviationsTab({ filters, onFilters }: Props) {
  const { data, isLoading, isError, error, refetch } = useDeviationsReport(filters)

  if (isError) {
    return (
      <Alert
        type="error"
        showIcon
        title="Could not load the protocol deviations report"
        description={error.message}
        action={<Button onClick={() => void refetch()}>Try again</Button>}
      />
    )
  }
  if (isLoading || !data) return <Skeleton active paragraph={{ rows: 10 }} />

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
        excelUrl={reportExportUrl('deviations', { study_id: filters.study_id, site_id: filters.site_id })}
        sync="simpletrials"
      />
      <div className="print-only">
        <Typography.Title level={2} style={{ margin: 0 }}>
          Protocol deviations report
        </Typography.Title>
        <Typography.Text type="secondary">
          {data.study_options.find((o) => o.id === filters.study_id)?.label ?? 'All studies'} · {formatDay(todayIso())}
        </Typography.Text>
      </div>
      {data.source.mode !== 'api' && <Alert type="warning" showIcon title="Demo data: SimpleTrials is not connected" />}
      {data.source.mode === 'api' && data.source.sandbox_only && (
        <Alert
          type="info"
          showIcon
          title="SimpleTrials sandbox study"
          description="Figures come from the sandbox study only. All studies appear once the Workspace (all studies) read-only key is enabled."
        />
      )}
      {!data.has_deviations && (
        <Alert
          type="info"
          showIcon
          title="No protocol deviations recorded in SimpleTrials yet"
          description="Once deviations are entered in SimpleTrials, press Sync now (or wait for the hourly sync) to see them here."
        />
      )}
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        {data.rules.source}
      </Typography.Text>

      <ReportTiles tiles={data.tiles} />

      <Flex gap={18} wrap>
        <ChartCard title="By severity" rule={data.rules.severity} flex="1 1 380px">
          <Counts rows={data.by_severity} colourFor={(l) => SEVERITY_COLOUR[l] ?? OTHER_COLOUR} testId="deviation-severity-row" empty="No deviations in this selection." />
        </ChartCard>
        <ChartCard title="By category" flex="1 1 380px">
          <Counts rows={data.by_category} colourFor={() => INK.info} testId="deviation-category-row" empty="No deviations in this selection." />
        </ChartCard>
      </Flex>

      <Flex gap={18} wrap>
        <ChartCard title="Monthly trend" rule={data.rules.trend} flex="2 1 520px">
          <Trend report={data} />
        </ChartCard>
        <ChartCard title="Open deviations by age" rule={data.rules.ageing} flex="1 1 300px">
          <Counts rows={data.ageing} colourFor={(l) => (l.startsWith('Over') ? INK.bad : l.startsWith('61') ? INK.warn : INK.info)} testId="deviation-ageing-row" empty="No open deviations." />
        </ChartCard>
      </Flex>

      <ChartCard title="Sites (highest rate first)" rule={data.rules.rate}>
        <Sites report={data} />
      </ChartCard>

      <ChartCard title={`All deviations (${data.deviations.length})`} rule="Open first, most severe first, then longest open.">
        <Table<DeviationRow>
          size="small"
          rowKey="id"
          dataSource={data.deviations}
          pagination={data.deviations.length > 25 ? { pageSize: 25, showSizeChanger: false } : false}
          scroll={{ x: 1100 }}
          locale={{ emptyText: 'No deviations in this selection.' }}
          onRow={() => ({ 'data-testid': 'deviation-row' }) as HTMLAttributes<HTMLElement>}
          columns={[
            { title: 'No.', dataIndex: 'number', width: 80, render: (v: string | null) => v ?? '—' },
            { title: 'Study', dataIndex: 'protocol_number', width: 130 },
            { title: 'Site', dataIndex: 'where', width: 180 },
            { title: 'Category', dataIndex: 'category', width: 150 },
            {
              title: 'Severity',
              dataIndex: 'severity',
              width: 100,
              render: (v: string) => <Tag color={SEVERITY_TAG[v] ?? 'default'}>{v}</Tag>,
            },
            {
              title: 'Description',
              key: 'description',
              render: (_, r) => (
                <Flex vertical gap={2}>
                  <span>{r.description ?? '—'}</span>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {r.subject_level ? 'Subject-level' : 'Site or study level'}
                    {r.reportable ? ' · Reportable to ethics' : ''}
                  </Typography.Text>
                </Flex>
              ),
            },
            { title: 'Occurred', dataIndex: 'occurred_on', width: 110, render: (v: string | null) => (v ? formatDay(v) : '—') },
            { title: 'Identified', dataIndex: 'identified_on', width: 110, render: (v: string | null) => (v ? formatDay(v) : '—') },
            {
              title: 'Status',
              key: 'status',
              width: 130,
              render: (_, r) =>
                r.closed ? (
                  <Tag>{r.status}{r.closed_on ? ` ${formatDay(r.closed_on)}` : ''}</Tag>
                ) : (
                  <Flex vertical gap={0}>
                    <Tag color="gold" style={{ marginInlineEnd: 0, width: 'fit-content' }}>{r.status}</Tag>
                    {r.days_open !== null && <Typography.Text type="secondary" style={{ fontSize: 12 }}>{r.days_open} days open</Typography.Text>}
                  </Flex>
                ),
            },
          ]}
        />
      </ChartCard>
    </Flex>
  )
}
