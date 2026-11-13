import { Alert, Button, Flex, Skeleton, Table, Tag, Typography } from 'antd'
import type { HTMLAttributes } from 'react'

import { reportExportUrl } from '../../api/client'
import { useRisksIssuesReport } from '../../api/hooks'
import type { IssueRow, ReportFilters, RisksIssuesReport } from '../../api/types'
import { formatDay } from '../../lib/format'
import { INK, todayIso } from '../../lib/reports'
import { Counts, monthLabel } from './DeviationsTab'
import { Bar, ChartCard, Legend, ReportTiles, ReportToolbar } from './ReportParts'

interface Props {
  filters: ReportFilters
  onFilters: (next: ReportFilters) => void
}

const GREY = '#8A97A8'
const CLOSED_COLOUR = '#3E8E5E'
const PRIORITY_COLOUR: Record<string, string> = {
  Critical: INK.bad,
  Urgent: INK.bad,
  High: INK.bad,
  Medium: INK.warn,
  Normal: INK.info,
  Low: GREY,
}
const PRIORITY_TAG: Record<string, string> = { Critical: 'red', Urgent: 'red', High: 'red', Medium: 'orange', Normal: 'blue' }

/** Monthly columns: opened next to closed. */
function Trend({ report }: { report: RisksIssuesReport }) {
  const max = Math.max(1, ...report.trend.map((m) => Math.max(m.opened, m.closed)))
  return (
    <Flex vertical gap={8}>
      <Flex align="flex-end" gap={6} style={{ height: 150 }} role="img" aria-label="Issues opened and closed by month">
        {report.trend.map((m) => (
          <Flex
            key={m.month}
            align="flex-end"
            justify="center"
            gap={2}
            data-testid="issue-month"
            title={`${monthLabel(m.month)}: ${m.opened} opened, ${m.closed} closed`}
            style={{ flex: '1 1 0', height: '100%', minWidth: 14 }}
          >
            <div style={{ width: '45%', height: `${(m.opened / max) * 130}px`, background: INK.warn, borderRadius: 2 }} />
            <div style={{ width: '45%', height: `${(m.closed / max) * 130}px`, background: CLOSED_COLOUR, borderRadius: 2 }} />
          </Flex>
        ))}
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
          { label: 'Opened', color: INK.warn },
          { label: 'Closed', color: CLOSED_COLOUR },
        ]}
      />
    </Flex>
  )
}

function Sites({ report }: { report: RisksIssuesReport }) {
  if (report.by_site.length === 0) return <Typography.Text type="secondary">No issues in this selection.</Typography.Text>
  const max = Math.max(1, ...report.by_site.map((s) => s.open))
  return (
    <Flex vertical gap={12}>
      {report.by_site.map((s) => (
        <Flex key={s.key} vertical gap={4} data-testid="issue-site-row">
          <Flex justify="space-between" gap={8} wrap>
            <span style={{ fontWeight: 600 }}>
              {s.label}{' '}
              <Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 400 }}>
                {s.protocol_number}
              </Typography.Text>
            </span>
            <span style={{ fontSize: 13 }}>
              <strong>{s.open} open</strong> ·{' '}
              {s.overdue ? <Typography.Text type="danger">{s.overdue} overdue</Typography.Text> : 'none overdue'} · {s.total} in all
            </span>
          </Flex>
          <Bar
            percent={(s.open / max) * 100}
            color={s.overdue ? INK.bad : INK.info}
            label={`${s.label}: ${s.open} open, ${s.overdue} overdue`}
          />
        </Flex>
      ))}
    </Flex>
  )
}

/** Risks and issues dashboard: SimpleTrials action items (the CTMS is the only source). */
export function RisksIssuesTab({ filters, onFilters }: Props) {
  const { data, isLoading, isError, error, refetch } = useRisksIssuesReport(filters)

  if (isError) {
    return (
      <Alert
        type="error"
        showIcon
        title="Could not load the risks and issues report"
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
        sync="simpletrials"
        excelUrl={reportExportUrl('risks-issues', { study_id: filters.study_id, site_id: filters.site_id })}
      />
      <div className="print-only">
        <Typography.Title level={2} style={{ margin: 0 }}>
          Risks and issues report
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
      {!data.has_issues && (
        <Alert
          type="info"
          showIcon
          title="No risks or issues recorded in SimpleTrials yet"
          description="Once action items are entered in SimpleTrials, press Sync now (or wait for the hourly sync) to see them here."
        />
      )}
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        {data.rules.source}
      </Typography.Text>

      <ReportTiles tiles={data.tiles} />

      <Flex gap={18} wrap>
        <ChartCard title="By priority" rule={data.rules.priority} flex="1 1 380px">
          <Counts
            rows={data.by_priority}
            colourFor={(l) => PRIORITY_COLOUR[l] ?? GREY}
            testId="issue-priority-row"
            empty="No issues in this selection."
          />
        </ChartCard>
        <ChartCard title="By category" flex="1 1 380px">
          <Counts rows={data.by_category} colourFor={() => INK.info} testId="issue-category-row" empty="No issues in this selection." />
        </ChartCard>
      </Flex>

      <Flex gap={18} wrap>
        <ChartCard title="Opened and closed by month" rule={data.rules.trend} flex="2 1 520px">
          <Trend report={data} />
        </ChartCard>
        <ChartCard title="Open issues by age" rule={data.rules.ageing} flex="1 1 300px">
          <Counts
            rows={data.ageing}
            colourFor={(l) => (l.startsWith('Over') ? INK.bad : l.startsWith('61') ? INK.warn : INK.info)}
            testId="issue-ageing-row"
            empty="No open issues."
          />
        </ChartCard>
      </Flex>

      <ChartCard title="Sites (most overdue first)" rule={data.rules.overdue}>
        <Sites report={data} />
      </ChartCard>

      <ChartCard title={`All risks and issues (${data.issues.length})`} rule="Open first, most overdue first, then by priority and due date.">
        <Table<IssueRow>
          size="small"
          rowKey="id"
          dataSource={data.issues}
          pagination={data.issues.length > 25 ? { pageSize: 25, showSizeChanger: false } : false}
          scroll={{ x: 1100 }}
          locale={{ emptyText: 'No issues in this selection.' }}
          onRow={() => ({ 'data-testid': 'issue-row' }) as HTMLAttributes<HTMLElement>}
          columns={[
            { title: 'No.', dataIndex: 'number', width: 60, render: (v: string | null) => v ?? '—' },
            { title: 'Study', dataIndex: 'protocol_number', width: 130 },
            { title: 'Site', dataIndex: 'where', width: 170 },
            {
              title: 'Issue',
              key: 'description',
              render: (_, r) => (
                <Flex vertical gap={2}>
                  <span>{r.description ?? '—'}</span>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {[r.category, r.subcategory].filter(Boolean).join(' · ')}
                    {r.response ? ` · Response: ${r.response}` : ''}
                  </Typography.Text>
                </Flex>
              ),
            },
            {
              title: 'Priority',
              dataIndex: 'priority',
              width: 100,
              render: (v: string) => <Tag color={PRIORITY_TAG[v] ?? 'default'}>{v}</Tag>,
            },
            { title: 'Assigned to', dataIndex: 'assignee', width: 140, render: (v: string | null) => v ?? '—' },
            { title: 'Opened', dataIndex: 'opened_on', width: 110, render: (v: string | null) => (v ? formatDay(v) : '—') },
            {
              title: 'Due',
              key: 'due',
              width: 140,
              render: (_, r) => (
                <Flex vertical gap={0}>
                  <span>{r.due_on ? formatDay(r.due_on) : '—'}</span>
                  {r.days_overdue !== null && (
                    <Typography.Text type="danger" style={{ fontSize: 12 }}>
                      {r.days_overdue} day{r.days_overdue === 1 ? '' : 's'} overdue
                    </Typography.Text>
                  )}
                </Flex>
              ),
            },
            {
              title: 'Status',
              key: 'status',
              width: 130,
              render: (_, r) =>
                r.closed ? (
                  <Tag>
                    {r.status}
                    {r.closed_on ? ` ${formatDay(r.closed_on)}` : ''}
                  </Tag>
                ) : (
                  <Tag color="gold">{r.status}</Tag>
                ),
            },
          ]}
        />
      </ChartCard>
    </Flex>
  )
}
