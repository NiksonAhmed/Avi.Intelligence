import { EditOutlined, LockOutlined, WarningOutlined } from '@ant-design/icons'
import { App, Button, Empty, Flex, Select, Table, Tooltip, Typography } from 'antd'
import type { TableColumnsType } from 'antd'
import { Link } from 'react-router'

import { useTaskStatus } from '../../api/hooks'
import { TASK_STATUSES } from '../../api/types'
import { assigneeSummary } from '../../lib/tasks'
import type { Task, TaskStatus } from '../../api/types'
import { formatDay } from '../../lib/format'
import { TASK_STATUS_STYLE } from '../../lib/studies'
import { ToneTag } from '../ToneTag'

const PERSON_STATUSES = TASK_STATUSES.filter((s) => s !== 'Cancelled')

interface Props {
  tasks: Task[]
  loading?: boolean
  /** Show the Category / About column (what each task is for). */
  showAbout?: boolean
  onEdit?: (task: Task) => void
  emptyText: string
}

/** What the task is about: its study, SOPs/forms, vendor, system, or "General". */
export function TaskAbout({ task }: { task: Task }) {
  const label = (
    <Typography.Text type="secondary" style={{ fontSize: 12, display: 'block' }}>
      {task.category_label}
    </Typography.Text>
  )
  if (task.category === 'study' && task.study) {
    return (
      <div>
        {label}
        <Link to={`/command-centre/${task.study.id}`}>{task.study.protocol_number}</Link>
      </div>
    )
  }
  if (task.category === 'sop') {
    return (
      <div>
        {label}
        {task.documents.map((d) => (
          <div key={d.sop_id}>
            <Link to={`/documents/sops/${encodeURIComponent(d.sop_id)}`}>
              {d.sop_number ?? d.title}
              {d.version ? ` v${d.version}` : ''}
            </Link>
          </div>
        ))}
      </div>
    )
  }
  return (
    <div>
      {label}
      {task.subject_name && <Typography.Text>{task.subject_name}</Typography.Text>}
    </div>
  )
}

function Progress({ task }: { task: Task }) {
  if (task.progress.total < 2) return null
  return (
    <Typography.Text type="secondary" style={{ fontSize: 12, display: 'block' }}>
      {task.progress.completed} of {task.progress.total} completed
    </Typography.Text>
  )
}

function StatusCell({ task }: { task: Task }) {
  const change = useTaskStatus()
  const { message } = App.useApp()
  const cancelled = task.status === 'Cancelled'
  // My own part, unless the task was cancelled (then only someone who may edit it can reopen it).
  const mine = task.my_status !== null && !(cancelled && !task.can_edit)
  const several = task.progress.total > 1

  if (!task.can_update_status || (cancelled && !task.can_edit)) {
    return (
      <div>
        <Tooltip title="Only the people this task is assigned to can update its status.">
          <span style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>
            <ToneTag tone={TASK_STATUS_STYLE[task.status]} />
            <LockOutlined aria-label="Read-only" style={{ color: '#5B6B82' }} />
          </span>
        </Tooltip>
        <Progress task={task} />
      </div>
    )
  }
  const value = mine && !cancelled ? task.my_status! : task.status
  const options = (mine ? PERSON_STATUSES : TASK_STATUSES).filter((s) => s !== 'Cancelled')
  return (
    <div>
      <Select<TaskStatus>
        size="small"
        aria-label={`Status of ${task.reference}`}
        value={value}
        loading={change.isPending}
        disabled={change.isPending}
        style={{ width: 140 }}
        onChange={(status) =>
          // mutateAsync, not per-call callbacks: a completed task leaves the list and this cell
          // unmounts, which would otherwise swallow the confirmation.
          void change
            .mutateAsync({ id: task.id, status })
            .then(() =>
              message.success(
                status === 'Cancelled'
                  ? `${task.reference} cancelled`
                  : mine && several
                    ? `Your part of ${task.reference} marked ${status}`
                    : `${task.reference} marked ${status}`,
              ),
            )
            .catch((e: Error) => message.error(e.message))
        }
        options={[...options, ...(task.can_edit ? (['Cancelled'] as const) : [])].map((s) => ({
          value: s,
          label: s,
        }))}
      />
      {several && (
        <Typography.Text type="secondary" style={{ fontSize: 12, display: 'block' }}>
          {mine && !cancelled ? 'Your part · ' : 'Sets everyone · '}
          {task.progress.completed} of {task.progress.total} completed
        </Typography.Text>
      )}
    </div>
  )
}

function AssigneesCell({ task }: { task: Task }) {
  const names = task.assignees.map((a) => a.name)
  if (task.assignees.length < 2) {
    return (
      <span>
        {names[0]}
        {task.own_task && (
          <Typography.Text type="secondary" style={{ fontSize: 12, display: 'block' }}>
            Own task
          </Typography.Text>
        )}
      </span>
    )
  }
  return (
    <Tooltip
      title={
        <div>
          {task.assignees.map((a) => (
            <div key={a.person_id}>
              {a.name}: {a.status}
            </div>
          ))}
        </div>
      }
    >
      <span style={{ textDecoration: 'underline dotted', cursor: 'help' }} tabIndex={0}>
        {assigneeSummary(names)}
      </span>
    </Tooltip>
  )
}

export function TaskTable({ tasks, loading, showAbout = false, onEdit, emptyText }: Props) {
  const anyEditable = tasks.some((t) => t.can_edit)
  const columns: TableColumnsType<Task> = [
    { title: 'Ref.', dataIndex: 'reference', width: 100 },
    {
      title: 'Task',
      dataIndex: 'title',
      render: (title: string, t) => (
        <div>
          <Typography.Text strong>{title}</Typography.Text>
          {t.plan_item && t.plan_item.name !== title && (
            <div>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                Plan: {t.plan_item.name}
              </Typography.Text>
            </div>
          )}
          {t.description && (
            <Typography.Paragraph type="secondary" ellipsis={{ rows: 2 }} style={{ margin: 0, fontSize: 13 }}>
              {t.description}
            </Typography.Paragraph>
          )}
        </div>
      ),
    },
    ...(showAbout
      ? [
          {
            title: 'About',
            key: 'about',
            width: 190,
            render: (_: unknown, t: Task) => <TaskAbout task={t} />,
          },
        ]
      : []),
    {
      title: 'Assigned to',
      key: 'assignees',
      width: 170,
      responsive: ['md'],
      render: (_: unknown, t: Task) => <AssigneesCell task={t} />,
    },
    {
      title: 'Due',
      dataIndex: 'due_date',
      width: 150,
      render: (due: string | null, t) => (
        <Flex gap={6} align="center" style={{ whiteSpace: 'nowrap' }}>
          {formatDay(due)}
          {t.overdue && (
            <ToneTag
              tone={{ label: 'Overdue', color: '#8A1C12', background: '#FDECEA', border: '#F1B0A8' }}
              icon={<WarningOutlined />}
              help="The due date has passed and the task is not completed or cancelled."
            />
          )}
        </Flex>
      ),
    },
    {
      title: 'Status',
      dataIndex: 'status',
      width: 170,
      render: (_: TaskStatus, t) => <StatusCell task={t} />,
    },
    ...(anyEditable && onEdit
      ? [
          {
            title: <span className="sr-only">Actions</span>,
            key: 'actions',
            width: 60,
            render: (_: unknown, t: Task) =>
              t.can_edit ? (
                <Button
                  type="text"
                  icon={<EditOutlined />}
                  aria-label={`Edit ${t.reference}`}
                  onClick={() => onEdit(t)}
                />
              ) : null,
          },
        ]
      : []),
  ]

  return (
    <Table<Task>
      rowKey="id"
      size="middle"
      columns={columns}
      dataSource={tasks}
      loading={loading}
      pagination={{ pageSize: 20, hideOnSinglePage: true, showSizeChanger: false }}
      locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={emptyText} /> }}
    />
  )
}
