import { Alert, App, DatePicker, Form, Input, Modal, Select } from 'antd'
import dayjs from 'dayjs'
import type { Dayjs } from 'dayjs'

import { useCreateTask, usePeople, useStudies, useUpdateTask } from '../../api/hooks'
import { TASK_STATUSES } from '../../api/types'
import type { PlanItemRef, Task, TaskStatus } from '../../api/types'

interface Props {
  open: boolean
  onClose: () => void
  /** Edit this task; omit to create a new one. */
  task?: Task | null
  defaultStudyId?: string
  /** Create the task for this study-plan entry (e.g. "01.01 Study Start"). */
  planItem?: PlanItemRef | null
}

interface Values {
  study_id: string
  title: string
  description?: string
  assignee_id: string
  due_date?: Dayjs | null
  status?: TaskStatus
}

/** Administrator form for creating, assigning and editing a task. */
export function TaskFormModal({ open, onClose, task, defaultStudyId, planItem }: Props) {
  const linked = task?.plan_item ?? planItem ?? null
  const [form] = Form.useForm<Values>()
  const studies = useStudies()
  const people = usePeople()
  const create = useCreateTask()
  const update = useUpdateTask()
  const { message } = App.useApp()
  const editing = Boolean(task)

  const submit = (v: Values) => {
    const due = v.due_date ? v.due_date.format('YYYY-MM-DD') : null
    const done = {
      onSuccess: () => {
        void message.success(editing ? 'Task updated' : 'Task created and assigned')
        onClose()
      },
      onError: (e: Error) => void message.error(e.message),
    }
    if (task) {
      update.mutate(
        {
          id: task.id,
          input: {
            title: v.title,
            description: v.description ?? null,
            assignee_id: v.assignee_id,
            due_date: due,
            ...(v.status ? { status: v.status } : {}),
          },
        },
        done,
      )
    } else {
      create.mutate(
        {
          study_id: v.study_id,
          plan_item_id: planItem?.external_id ?? null,
          title: v.title,
          description: v.description ?? null,
          assignee_id: v.assignee_id,
          due_date: due,
        },
        done,
      )
    }
  }

  return (
    <Modal
      open={open}
      title={task ? `Edit ${task.reference}` : 'New task'}
      okText={task ? 'Save changes' : 'Create task'}
      onOk={() => form.submit()}
      onCancel={onClose}
      confirmLoading={create.isPending || update.isPending}
      destroyOnHidden
    >
      <Form<Values>
        form={form}
        layout="vertical"
        onFinish={submit}
        preserve={false}
        initialValues={
          task
            ? {
                study_id: task.study.id,
                title: task.title,
                description: task.description ?? undefined,
                assignee_id: task.assignee_id,
                due_date: task.due_date ? dayjs(task.due_date) : null,
                status: task.status,
              }
            : { study_id: defaultStudyId, title: planItem?.name }
        }
      >
        {linked && (
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
            title={`For plan item: ${linked.name}`}
            description="Completing this task does not change SimpleTrials. Its % complete there is updated separately."
          />
        )}
        <Form.Item name="study_id" label="Study" rules={[{ required: true, message: 'Choose a study' }]}>
          <Select
            disabled={editing}
            loading={studies.isLoading}
            placeholder="Choose a study"
            options={(studies.data?.studies ?? []).map((s) => ({
              value: s.id,
              label: `${s.protocol_number} · ${s.title}`,
            }))}
          />
        </Form.Item>
        <Form.Item
          name="title"
          label="Task"
          rules={[{ required: true, whitespace: true, min: 3, message: 'Describe the task (3+ characters)' }]}
        >
          <Input maxLength={300} placeholder="e.g. Collect signed CVs for site 102" />
        </Form.Item>
        <Form.Item name="description" label="Details (optional)">
          <Input.TextArea rows={3} maxLength={5000} />
        </Form.Item>
        <Form.Item name="assignee_id" label="Assign to" rules={[{ required: true, message: 'Choose a person' }]}>
          <Select
            showSearch={{ optionFilterProp: 'label' }}
            loading={people.isLoading}
            placeholder="Choose a person"
            options={(people.data ?? []).map((p) => ({ value: p.id, label: `${p.name} (${p.job_title})` }))}
          />
        </Form.Item>
        <Form.Item name="due_date" label="Due date (optional)">
          <DatePicker format="DD MMM YYYY" style={{ width: '100%' }} />
        </Form.Item>
        {editing && (
          <Form.Item name="status" label="Status">
            <Select options={TASK_STATUSES.map((s) => ({ value: s, label: s }))} />
          </Form.Item>
        )}
      </Form>
    </Modal>
  )
}
