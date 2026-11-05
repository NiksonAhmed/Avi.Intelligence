import { PlusOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Checkbox, Col, Flex, Row, Segmented, Statistic, Typography } from 'antd'
import { useState } from 'react'
import { useSearchParams } from 'react-router'

import { useTasks } from '../../api/hooks'
import type { Task } from '../../api/types'
import { PageHeader } from '../../components/PageHeader'
import { TaskFormModal } from '../../components/work/TaskFormModal'
import { TaskTable } from '../../components/work/TaskTable'
import { taskBucket } from '../../lib/studies'

type Scope = 'me' | 'all'

export function MyTasksPage() {
  const [params, setParams] = useSearchParams()
  const scope: Scope = params.get('scope') === 'all' ? 'all' : 'me'
  const includeClosed = params.get('closed') === '1'
  const { data, isLoading, isError, error, refetch } = useTasks({
    assignee: scope === 'me' ? 'me' : undefined,
    include_closed: includeClosed,
  })
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

  return (
    <>
      <PageHeader
        title="My Tasks"
        subtitle="Tasks assigned to you across all studies. You can update the status of your own tasks."
        extra={
          canManage && (
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
          <Checkbox checked={includeClosed} onChange={(e) => setParam('closed', e.target.checked ? '1' : null)}>
            Show completed and cancelled
          </Checkbox>
          {scope === 'all' && !canManage && (
            <Typography.Text type="secondary">Tasks assigned to others are read-only.</Typography.Text>
          )}
        </Flex>
        <TaskTable
          tasks={tasks}
          loading={isLoading}
          canManage={canManage}
          showStudy
          onEdit={(task) => setModal({ open: true, task })}
          emptyText={
            scope === 'me'
              ? 'Nothing assigned to you. Tasks an administrator assigns to you will appear here.'
              : 'No tasks yet.'
          }
        />
      </Card>

      <TaskFormModal open={modal.open} task={modal.task} onClose={() => setModal({ open: false })} />
    </>
  )
}
