import { EditOutlined, LockOutlined, WarningOutlined } from '@ant-design/icons'
import { App, Button, Empty, Flex, Select, Table, Tooltip, Typography } from 'antd'
import type { TableColumnsType } from 'antd'
import { Link } from 'react-router'

import { useTaskStatus } from '../../api/hooks'
import { TASK_STATUSES } from '../../api/types'
import type { Task, TaskStatus } from '../../api/types'
import { formatDay } from '../../lib/format'
import { TASK_STATUS_STYLE } from '../../lib/studies'
import { ToneTag } from '../ToneTag'

interface Props {
  tasks: Task[]
  loading?: boolean
  canManage: boolean
  showStudy?: boolean
  onEdit?: (task: Task) => void
  emptyText: string
}

function StatusCell({ task, canManage }: { task: Task; canManage: boolean }) {
  const change = useTaskStatus()
  const { message } = App.useApp()
  if (!task.can_update_status) {
    return (
      <Tooltip title="Only the person this task is assigned to can update its status.">
        <span style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>
          <ToneTag tone={TASK_STATUS_STYLE[task.status]} />
          <LockOutlined aria-label="Read-only" style={{ color: '#5B6B82' }} />
        </span>
      </Tooltip>
    )
  }
  return (
    <Select<TaskStatus>
      size="small"
      aria-label={`Status of ${task.reference}`}
      value={task.status}
      loading={change.isPending}
      disabled={change.isPending}
      style={{ width: 140 }}
      onChange={(status) =>
        // mutateAsync, not per-call callbacks: a completed task leaves the list and this cell
        // unmounts, which would otherwise swallow the confirmation.
        void change
          .mutateAsync({ id: task.id, status })
          .then(() => message.success(`${task.reference} marked ${status}`))
          .catch((e: Error) => message.error(e.message))
      }
      options={TASK_STATUSES.filter((s) => canManage || s !== 'Cancelled').map((s) => ({
        value: s,
        label: s,
      }))}
    />
  )
}

export function TaskTable({ tasks, loading, canManage, showStudy = false, onEdit, emptyText }: Props) {
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
    ...(showStudy
      ? [
          {
            title: 'Study',
            key: 'study',
            width: 150,
            responsive: ['md' as const],
            render: (_: unknown, t: Task) => (
              <Link to={`/command-centre/${t.study.id}`}>{t.study.protocol_number}</Link>
            ),
          },
        ]
      : []),
    { title: 'Assigned to', dataIndex: 'assignee_name', width: 170, responsive: ['md'] },
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
      render: (_: TaskStatus, t) => <StatusCell task={t} canManage={canManage} />,
    },
    ...(canManage && onEdit
      ? [
          {
            title: <span className="sr-only">Actions</span>,
            key: 'actions',
            width: 60,
            render: (_: unknown, t: Task) => (
              <Button
                type="text"
                icon={<EditOutlined />}
                aria-label={`Edit ${t.reference}`}
                onClick={() => onEdit(t)}
              />
            ),
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
