import { PlusOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Checkbox, Col, Flex, Row, Segmented, Select, Statistic, Typography } from 'antd'
import { useState } from 'react'
import { useSearchParams } from 'react-router'

import { useTasks } from '../../api/hooks'
import { TASK_CATEGORY_LABELS } from '../../api/types'
import type { Task, TaskCategory } from '../../api/types'
import { PageHeader } from '../../components/PageHeader'
import { TaskFormModal } from '../../components/work/TaskFormModal'
import { useCreatableCategories } from '../../lib/tasks'
import { TaskTable } from '../../components/work/TaskTable'
import { taskBucket } from '../../lib/studies'

type Scope = 'me' | 'all'

export function MyTasksPage() {
  const [params, setParams] = useSearchParams()
  const scope: Scope = params.get('scope') === 'all' ? 'all' : 'me'
  const includeClosed = params.get('closed') === '1'
  const categoryParam = params.get('category')
  const category = categoryParam && categoryParam in TASK_CATEGORY_LABELS ? (categoryParam as TaskCategory) : undefined
  const { data, isLoading, isError, error, refetch } = useTasks({
    assignee: scope === 'me' ? 'me' : undefined,
    category,
    include_closed: includeClosed,
  })
  const creatable = useCreatableCategories()
  const [modal, setModal] = useState<{ open: boolean; task?: Task | null }>({ open: false })

  const setParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }

  const tasks = data?.tasks ?? []
  const open = tasks.filter((t) => t.status !== 'Completed' && t.status !== 'Cancelled')
  const overdue = open.filter((t) => taskBucket(t.due_date, t.overdue) === 'overdue').length
  const thisWeek = open.filter((t) => taskBucket(t.due_date, t.overdue) === 'week').length
  const canManage = Boolean(data?.can_manage)
  const canCreate = (data?.can_create ?? creatable).length > 0

  return (
    <>
      <PageHeader
        title="My Tasks"
        subtitle="Tasks assigned to you: studies, procedures and SOPs, vendors, computer systems and general work. Update your own part of each task, or add a task for your own tracking."
        extra={
          canCreate && (
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setModal({ open: true })}>
              New task
            </Button>
          )
        }
      />

      {isError && (
        <Alert
          type="error"
          showIcon
          style={{ marginBottom: 16 }}
          title="Could not load tasks"
          description={error.message}
          action={<Button onClick={() => void refetch()}>Try again</Button>}
        />
      )}

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        {[
          { label: scope === 'me' ? 'My open tasks' : 'Open tasks', value: open.length },
          { label: 'Overdue', value: overdue },
          { label: 'Due within 7 days', value: thisWeek },
        ].map((s) => (
          <Col key={s.label} xs={8}>
            <Card size="small" loading={isLoading}>
              <Statistic title={s.label} value={s.value} />
            </Card>
          </Col>
        ))}
      </Row>

      <Card>
        <Flex gap={16} wrap align="center" style={{ marginBottom: 16 }}>
          <Segmented<Scope>
            aria-label="Whose tasks"
            value={scope}
            onChange={(v) => setParam('scope', v === 'all' ? 'all' : null)}
            options={[
              { value: 'me', label: 'Assigned to me' },
              { value: 'all', label: 'All tasks' },
            ]}
          />
          <Select<TaskCategory | 'all'>
            aria-label="Filter by category"
            value={category ?? 'all'}
            style={{ minWidth: 200 }}
            onChange={(v) => setParam('category', v === 'all' ? null : v)}
            options={[
              { value: 'all', label: 'All categories' },
              ...(Object.keys(TASK_CATEGORY_LABELS) as TaskCategory[]).map((c) => ({
                value: c,
                label: TASK_CATEGORY_LABELS[c],
              })),
            ]}
          />
          <Checkbox checked={includeClosed} onChange={(e) => setParam('closed', e.target.checked ? '1' : null)}>
            Show completed and cancelled
          </Checkbox>
          {scope === 'all' && !canManage && (
            <Typography.Text type="secondary">
              Tasks assigned to others are read-only unless you can manage them.
            </Typography.Text>
          )}
        </Flex>
        <TaskTable
          tasks={tasks}
          loading={isLoading}
          showAbout
          onEdit={(task) => setModal({ open: true, task })}
          emptyText={
            scope === 'me'
              ? 'Nothing assigned to you. Tasks assigned to you, and tasks you add for yourself, appear here.'
              : 'No tasks yet.'
          }
        />
      </Card>

      <TaskFormModal open={modal.open} task={modal.task} onClose={() => setModal({ open: false })} />
    </>
  )
}
