import { PlusOutlined } from '@ant-design/icons'
import { Alert, Button, Card } from 'antd'
import { useState } from 'react'

import { useTasks } from '../../api/hooks'
import type { SopDocument, Task } from '../../api/types'
import { useCreatableCategories } from '../../lib/tasks'
import { TaskFormModal } from './TaskFormModal'
import { TaskTable } from './TaskTable'

/** Open Procedures and SOPs tasks about this SOP or form, with "New task" for admins and QA. */
export function SopTasksCard({ doc }: { doc: SopDocument }) {
  const tasks = useTasks({ sop_id: doc.id })
  const canCreate = useCreatableCategories().includes('sop') && doc.status === 'Effective'
  const [modal, setModal] = useState<{ open: boolean; task?: Task | null }>({ open: false })
  const what = doc.kind === 'form' ? 'form' : 'SOP'

  return (
    <Card
      title={`Tasks for this ${what}`}
      style={{ marginTop: 16 }}
      extra={
        canCreate && (
          <Button icon={<PlusOutlined />} onClick={() => setModal({ open: true })}>
            New task
          </Button>
        )
      }
    >
      {tasks.isError ? (
        <Alert type="error" showIcon title="Could not load tasks" description={tasks.error.message} />
      ) : (
        <TaskTable
          tasks={tasks.data?.tasks ?? []}
          loading={tasks.isLoading}
          onEdit={(task) => setModal({ open: true, task })}
          emptyText={`No open tasks for this ${what}.`}
        />
      )}
      <TaskFormModal
        open={modal.open}
        task={modal.task}
        defaultDocumentIds={modal.task ? undefined : [doc.id]}
        onClose={() => setModal({ open: false })}
      />
    </Card>
  )
}
