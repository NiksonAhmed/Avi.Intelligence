import { Alert, Button, Empty, Flex, Skeleton, Typography } from 'antd'

import { reportExportUrl } from '../../api/client'
import { useWorkManagement } from '../../api/hooks'
import type {
  TaskCategory,
  WorkManagementReport,
  WorkPersonLoad,
  WorkReportFilters,
  WorkStatusCounts,
} from '../../api/types'
import { ToneTag } from '../../components/ToneTag'
import { formatDay } from '../../lib/format'
import { INK, todayIso, toneStyle } from '../../lib/reports'
import { ChartCard, Legend, ReportTiles, ReportToolbar, StackedBar } from './ReportParts'

interface Props {
  filters: WorkReportFilters
  onFilters: (next: WorkReportFilters) => void
}

const NOT_STARTED = '#8A97A8'
const STATUS_KEY = [
  { label: 'Not started', color: NOT_STARTED },
  { label: 'In progress', color: INK.info },
  { label: 'Blocked', color: INK.warn },
]

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? '' : 's'}`
}

/** One row per category or study: open tasks by status, with the overdue count beside it. */
export function StatusRows({ rows, empty, testId }: { rows: WorkStatusCounts[]; empty: string; testId: string }) {
  if (rows.length === 0) return <Empty description={empty} />
  const max = Math.max(1, ...rows.map((r) => r.total))
  return (
    <Flex vertical gap={10}>
      {rows.map((r) => {
        const label =
          `${r.label}: ${plural(r.total, 'open task')} (${r.not_started} not started, ${r.in_progress} in progress, ` +
          `${r.blocked} blocked), ${r.overdue} overdue`
        return (
          <Flex key={r.key} gap={12} align="center" data-testid={testId}>
            <span style={{ width: 150, flexShrink: 0, fontWeight: 600 }}>{r.label}</span>
            <div style={{ flex: '1 1 auto', minWidth: 80 }}>
              <StackedBar
                max={max}
                label={label}
                segments={[
                  { value: r.not_started, color: NOT_STARTED },
                  { value: r.in_progress, color: INK.info },
                  { value: r.blocked, color: INK.warn },
                ]}
              />
            </div>
            <span style={{ width: 130, flexShrink: 0, textAlign: 'right', fontSize: 13, whiteSpace: 'nowrap' }}>
              <strong>{r.total}</strong> open
              {r.overdue > 0 && <span style={{ color: INK.bad, fontWeight: 700 }}> · {r.overdue} overdue</span>}
            </span>
          </Flex>
        )
      })}
    </Flex>
  )
}

function PeopleRows({ people }: { people: WorkPersonLoad[] }) {
  if (people.length === 0) return <Empty description="Nobody has open tasks in this selection." />
  const max = Math.max(1, ...people.map((p) => p.open))
  return (
    <Flex vertical gap={10}>
      {people.map((p) => {
        const other = p.open - p.overdue - p.due_soon
        const label =
          `${p.name}: ${plural(p.open, 'open task')}, ${p.overdue} overdue, ${p.due_soon} due soon` +
          (p.blocked ? `, ${p.blocked} blocked` : '')
        return (
          <Flex key={p.person_id} gap={12} align="center" data-testid="person-row">
            <span style={{ width: 150, flexShrink: 0, fontWeight: 600 }}>{p.name}</span>
            <div style={{ flex: '1 1 auto', minWidth: 80 }}>
              <StackedBar
                max={max}
                label={label}
                segments={[
                  { value: p.overdue, color: INK.bad },
                  { value: p.due_soon, color: INK.warn },
                  { value: other, color: INK.info },
                ]}
              />
            </div>
            <span style={{ width: 130, flexShrink: 0, textAlign: 'right', fontSize: 13, whiteSpace: 'nowrap' }}>
              <strong>{p.open}</strong> open
              {p.overdue > 0 && <span style={{ color: INK.bad, fontWeight: 700 }}> · {p.overdue} overdue</span>}
            </span>
          </Flex>
        )
      })}
    </Flex>
  )
}

function OverdueList({ report }: { report: WorkManagementReport }) {
  if (report.overdue.length === 0) {
    return <Typography.Text type="secondary">No overdue tasks in this selection.</Typography.Text>
  }
  return (
    <Flex vertical>
      {report.overdue.map((t) => (
        <Flex
          key={t.task_id}
          justify="space-between"
          align="center"
          gap={8}
          data-testid="overdue-row"
          style={{ padding: '8px 0', borderTop: '1px solid #EEF1F5' }}
        >
          <Flex vertical style={{ minWidth: 0 }}>
            <span style={{ fontWeight: 600 }}>
              {t.reference} · {t.title}
            </span>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {t.category_label}
              {t.about ? ` · ${t.about}` : ''} · Due {formatDay(t.due_date)} · Waiting on{' '}
              {t.waiting_on.join(', ') || '—'}
            </Typography.Text>
          </Flex>
          <ToneTag tone={toneStyle('bad', `${plural(t.days_overdue, 'day')} late`)} />
        </Flex>
      ))}
    </Flex>
  )
}

export function WorkManagementTab({ filters, onFilters }: Props) {
  const { data, isLoading, isError, error, refetch } = useWorkManagement(filters)

  if (isError) {
    return (
      <Alert
        type="error"
        showIcon
        title="Could not load the Work management report"
        description={error.message}
        action={<Button onClick={() => void refetch()}>Try again</Button>}
      />
    )
  }
  if (isLoading || !data) return <Skeleton active paragraph={{ rows: 10 }} />

  const showStudies = !filters.category || filters.category === 'study'
  const scope = [
    data.study_options.find((o) => o.id === filters.study_id)?.label ?? 'All studies',
    data.category_options.find((o) => o.id === filters.category)?.label,
  ]
    .filter(Boolean)
    .join(' · ')
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
            onChange: (id) => onFilters({ ...filters, study_id: id }),
            width: 300,
          },
          {
            id: 'report-category',
            label: 'Task category',
            ariaLabel: 'Filter by task category',
            placeholder: 'All categories',
            value: filters.category,
            options: data.category_options,
            onChange: (c) => onFilters({ ...filters, category: c as TaskCategory | undefined }),
            width: 220,
          },
        ]}
        sourceText="Live figures · Source: Avi.Intelligence tasks"
        sync="live"
        excelUrl={reportExportUrl('work-management', { study_id: filters.study_id, category: filters.category })}
      />
      <div className="print-only">
        <Typography.Title level={2} style={{ margin: 0 }}>
          Work management report
        </Typography.Title>
        <Typography.Text type="secondary">
          {scope} · {formatDay(todayIso())}
        </Typography.Text>
      </div>

      <ReportTiles tiles={data.tiles} />

      <Flex gap={18} wrap>
        <ChartCard
          title="Open tasks by category"
          rule={`${data.rules.open ?? ''} ${data.rules.task_overdue ?? ''}`.trim()}
          extra={<Legend items={STATUS_KEY} />}
          flex="1 1 480px"
        >
          <StatusRows rows={data.by_category} empty="No task categories." testId="category-row" />
        </ChartCard>
        {showStudies && (
          <ChartCard title="Open study tasks by study" extra={<Legend items={STATUS_KEY} />} flex="1 1 480px">
            <StatusRows rows={data.by_study} empty="No studies in this selection." testId="study-row" />
          </ChartCard>
        )}
      </Flex>

      <Flex gap={18} wrap>
        <ChartCard
          title="Open work by person"
          rule={data.rules.by_person}
          extra={
            <Legend
              items={[
                { label: 'Overdue', color: INK.bad },
                { label: 'Due soon', color: INK.warn },
                { label: 'Other open', color: INK.info },
              ]}
            />
          }
          flex="1 1 480px"
        >
          <PeopleRows people={data.by_person} />
        </ChartCard>
        <ChartCard title="Overdue tasks" rule={data.rules.due_soon} flex="1 1 480px">
          <OverdueList report={data} />
        </ChartCard>
      </Flex>

      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        {data.rules.completed}
      </Typography.Text>
    </Flex>
  )
}
