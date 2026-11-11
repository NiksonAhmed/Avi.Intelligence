import { CheckCircleFilled, StarFilled, UserAddOutlined } from '@ant-design/icons'
import { Button, Empty, Flex, Segmented, Select, Table, Tooltip, Typography } from 'antd'
import type { TableColumnsType } from 'antd'
import { useState } from 'react'

import type { Milestone, MilestoneState, Rules, ScheduleState, Task } from '../api/types'
import { formatDay, formatDayShort } from '../lib/format'
import {
  MILESTONE_STATE,
  MILESTONE_STATE_RULE,
  SCHEDULE_STATE,
  TASK_STATUS_STYLE,
  scheduleLabel,
} from '../lib/studies'
import { ToneTag } from './ToneTag'

type Row = Milestone & { children?: Row[] }
type View = 'key' | 'full'

const START_LATER = { label: '', color: '#7A4A00', background: '#FDF3E1', border: '#EDC98A' }
const START_EARLIER = { label: '', color: '#1A4475', background: '#E8F0FB', border: '#A9C4EA' }
/** Below this width the table scrolls sideways instead of squeezing (e.g. tablet portrait). */
const MIN_TABLE_WIDTH = 900

/** Nest plan entries under their phase, keeping SimpleTrials order. */
function toTree(items: Milestone[]): Row[] {
  const byId = new Map<string, Row>(items.map((m) => [m.external_id, { ...m }]))
  const roots: Row[] = []
  for (const m of items) {
    const row = byId.get(m.external_id)!
    const parent = m.parent_external_id ? byId.get(m.parent_external_id) : undefined
    if (parent) (parent.children ??= []).push(row)
    else roots.push(row)
  }
  return roots
}

const PROGRESS_OPTIONS: MilestoneState[] = ['overdue', 'due_soon', 'in_progress', 'not_started', 'upcoming', 'completed']
const SCHEDULE_OPTIONS: { value: ScheduleState; label: string }[] = [
  { value: 'slipped_major', label: 'Slipped more than 30 days' },
  { value: 'slipped', label: 'Slipped up to 30 days' },
  { value: 'on_plan', label: 'On plan' },
  { value: 'ahead', label: 'Ahead' },
  { value: 'no_baseline', label: 'No original date' },
]

interface Props {
  items: Milestone[]
  rules: Rules
  /** Avi.Intelligence tasks of this study (closed included); those linked to a plan entry show in the Task column. */
  tasks?: Task[]
  canManage?: boolean
  onAssign?: (item: Milestone) => void
}

/** A date in a dense table: short form, full date on hover. */
function Day({ value }: { value: string | null }) {
  if (!value) return <Typography.Text type="secondary">—</Typography.Text>
  return (
    <Tooltip title={formatDay(value)}>
      <span style={{ whiteSpace: 'nowrap' }}>{formatDayShort(value)}</span>
    </Tooltip>
  )
}

function LinkedTask({ task }: { task: Task }) {
  const tone =
    task.status === 'Completed'
      ? TASK_STATUS_STYLE.Completed
      : task.overdue
        ? { ...TASK_STATUS_STYLE.Blocked, label: 'Overdue' }
        : TASK_STATUS_STYLE[task.status]
  return (
    <Tooltip title={`${task.reference}: ${task.title}${task.due_date ? ` · due ${formatDay(task.due_date)}` : ''}`}>
      <div
        data-testid={`plan-task-${task.reference}`}
        style={{
          padding: '3px 8px',
          borderRadius: 6,
          border: `1px solid ${tone.border}`,
          background: tone.background,
          color: tone.color,
          lineHeight: 1.4,
          fontSize: 12,
          maxWidth: '100%',
          overflowWrap: 'anywhere',
        }}
      >
        <div style={{ fontWeight: 600 }}>
          {task.status === 'Completed' && <CheckCircleFilled style={{ marginRight: 4 }} aria-hidden />}
          {task.assignees.map((a) => a.name).join(', ')}
        </div>
        <div>{task.due_date ? `Due ${formatDayShort(task.due_date)}` : 'No due date'}</div>
        <div style={{ fontWeight: 600 }}>{tone.label}</div>
      </div>
    </Tooltip>
  )
}

/**
 * The study plan as in SimpleTrials ("Milestones & Tasks"), with two statuses per row:
 * Progress (against the current end date) and Schedule (current vs original end date).
 */
export function PlanTable({ items, rules, tasks = [], canManage = false, onAssign }: Props) {
  const tasksByItem = new Map<string, Task[]>()
  for (const t of tasks) {
    if (!t.plan_item) continue
    const list = tasksByItem.get(t.plan_item.external_id) ?? []
    list.push(t)
    tasksByItem.set(t.plan_item.external_id, list)
  }
  const hasKey = items.some((m) => m.is_key)
  const [view, setView] = useState<View>(hasKey ? 'key' : 'full')
  const [progress, setProgress] = useState<MilestoneState[]>([])
  const [schedule, setSchedule] = useState<ScheduleState[]>([])
  const filtering = progress.length > 0 || schedule.length > 0

  const visible = items.filter(
    (m) =>
      (view === 'full' || (m.is_key && m.kind === 'milestone')) &&
      (progress.length === 0 || progress.includes(m.state)) &&
      (schedule.length === 0 || schedule.includes(m.schedule)),
  )
  // Hierarchy only for the unfiltered full plan; filtered results and key milestones are flat lists.
  const data: Row[] = view === 'full' && !filtering ? toTree(visible) : visible
  const hasStart = items.some((m) => m.start_date)
  const hasBaselineStart = items.some((m) => m.baseline_start_date)
  const hasBaseline = items.some((m) => m.baseline_date)
  const hasPercent = items.some((m) => m.percent_complete !== null)
  const hasActual = items.some((m) => m.actual_date)

  const startChildren: TableColumnsType<Row> = [
    ...(hasBaselineStart
      ? [
          {
            title: 'Original',
            dataIndex: 'baseline_start_date',
            width: 82,
            render: (d: string | null) => <Day value={d} />,
          },
        ]
      : []),
    {
      title: hasBaselineStart ? 'Current' : 'Date',
      dataIndex: 'start_date',
      width: 88,
      render: (d: string | null, m: Row) => (
        <div>
          <Day value={d} />
          {m.start_variance_days ? (
            <div>
              <ToneTag tone={m.start_variance_days > 0 ? START_LATER : START_EARLIER} help={rules.start_moved}>
                {m.start_variance_days > 0 ? `+${m.start_variance_days}d` : `−${Math.abs(m.start_variance_days)}d`}
              </ToneTag>
            </div>
          ) : null}
        </div>
      ),
    },
  ]

  const endChildren: TableColumnsType<Row> = [
    ...(hasBaseline
      ? [
          {
            title: 'Original',
            dataIndex: 'baseline_date',
            width: 82,
            render: (d: string | null) => <Day value={d} />,
          },
        ]
      : []),
    {
      title: hasBaseline ? 'Current' : 'Date',
      dataIndex: 'planned_date',
      width: 82,
      render: (d: string | null) => <Day value={d} />,
    },
    ...(hasActual
      ? [{ title: 'Actual', dataIndex: 'actual_date', width: 82, render: (d: string | null) => <Day value={d} /> }]
      : []),
  ]

  const columns: TableColumnsType<Row> = [
    {
      title: 'Milestone / task',
      dataIndex: 'name',
      render: (name: string, m) => (
        <div style={{ minWidth: 160 }}>
          <Flex gap={6} align="flex-start">
            {m.is_key && (
              <Tooltip title={rules.key_milestone}>
                <StarFilled aria-label="Key milestone" style={{ color: '#B26B00', marginTop: 4 }} />
              </Tooltip>
            )}
            <span style={m.kind === 'phase' ? { fontWeight: 600 } : undefined}>{name}</span>
          </Flex>
          {(view === 'key' || filtering) && m.phase && (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {m.phase}
            </Typography.Text>
          )}
        </div>
      ),
    },
    ...(hasStart
      ? [{ title: <Tooltip title="Start date: original (baseline) and current plan">Start</Tooltip>, children: startChildren }]
      : []),
    {
      title: <Tooltip title="End date: original (baseline) and current plan">End</Tooltip>,
      children: endChildren,
    },
    ...(hasPercent
      ? [
          {
            title: '%',
            dataIndex: 'percent_complete',
            width: 52,
            render: (p: number | null) => (p === null ? '—' : `${p}%`),
          },
        ]
      : []),
    {
      title: <Tooltip title="Against the current end date and today">Progress</Tooltip>,
      dataIndex: 'state',
      width: 104,
      render: (_: unknown, m) => {
        const rule = MILESTONE_STATE_RULE[m.state]
        return <ToneTag tone={MILESTONE_STATE[m.state]} help={rule ? rules[rule] : undefined} />
      },
    },
    ...(hasBaseline
      ? [
          {
            title: <Tooltip title="Current end date compared with the original end date">Schedule</Tooltip>,
            dataIndex: 'schedule',
            width: 96,
            render: (_: unknown, m: Row) => {
              const style = SCHEDULE_STATE[m.schedule]
              return (
                <ToneTag tone={style} help={rules[style.rule]}>
                  {scheduleLabel(m.schedule, m.variance_days)}
                </ToneTag>
              )
            },
          },
        ]
      : []),
    {
      title: <Tooltip title="Avi.Intelligence task assigned for this item (does not change SimpleTrials)">Task</Tooltip>,
      key: 'task',
      width: 132,
      render: (_: unknown, m: Row) => {
        const linked = tasksByItem.get(m.external_id) ?? []
        if (linked.length > 0) {
          return (
            <Flex vertical gap={4}>
              {linked.map((t) => (
                <LinkedTask key={t.id} task={t} />
              ))}
            </Flex>
          )
        }
        // Phase headings only group the plan; tasks are assigned to their milestones and tasks.
        if (m.kind === 'phase') return null
        return canManage && onAssign ? (
          <Button
            size="small"
            type="dashed"
            icon={<UserAddOutlined />}
            aria-label={`Assign a task for ${m.name}`}
            onClick={() => onAssign(m)}
          >
            Assign
          </Button>
        ) : (
          <Typography.Text type="secondary">—</Typography.Text>
        )
      },
    },
  ]

  return (
    <>
      <Flex gap={12} wrap align="center" style={{ marginBottom: 12 }}>
        <Segmented<View>
          aria-label="Plan view"
          value={view}
          onChange={setView}
          options={[
            { value: 'key', label: 'Key milestones', disabled: !hasKey },
            { value: 'full', label: 'Full plan' },
          ]}
        />
        <Select<MilestoneState[]>
          mode="multiple"
          allowClear
          aria-label="Filter by progress"
          placeholder="Progress: all"
          value={progress}
          onChange={setProgress}
          options={PROGRESS_OPTIONS.map((s) => ({ value: s, label: MILESTONE_STATE[s].label }))}
          style={{ minWidth: 180 }}
        />
        {hasBaseline && (
          <Select<ScheduleState[]>
            mode="multiple"
            allowClear
            aria-label="Filter by schedule"
            placeholder="Schedule: all"
            value={schedule}
            onChange={setSchedule}
            options={SCHEDULE_OPTIONS}
            style={{ minWidth: 200 }}
          />
        )}
        <Typography.Text type="secondary">
          {visible.filter((m) => m.kind !== 'phase').length} shown
        </Typography.Text>
      </Flex>
      <Table<Row>
        rowKey="id"
        size="small"
        bordered={false}
        pagination={false}
        columns={columns}
        dataSource={data}
        expandable={{ defaultExpandAllRows: true }}
        scroll={{ x: MIN_TABLE_WIDTH }}
        key={`${view}-${filtering}`}
        locale={{
          emptyText: (
            <Empty
              description={
                items.length === 0 ? 'SimpleTrials has no milestones or tasks for this study.' : 'Nothing matches these filters.'
              }
            />
          ),
        }}
      />
    </>
  )
}
