import { Alert, App, DatePicker, Form, Input, Modal, Select, Typography } from 'antd'
import dayjs from 'dayjs'
import { useEffect } from 'react'
import type { Dayjs } from 'dayjs'

import { useCreateTask, usePeople, useSops, useStudies, useUpdateTask } from '../../api/hooks'
import { TASK_CATEGORY_LABELS, TASK_STATUSES } from '../../api/types'
import type { PlanItemRef, Task, TaskCategory, TaskStatus } from '../../api/types'
import { sopOptions, useTaskRights } from '../../lib/tasks'

interface Props {
  open: boolean
  onClose: () => void
  /** Edit this task; omit to create a new one. */
  task?: Task | null
  /** Create a Study task for this study (category fixed). */
  defaultStudyId?: string
  /** Create the task for this study-plan entry (e.g. "01.01 Study Start"). */
  planItem?: PlanItemRef | null
  /** Create a Procedures and SOPs task about these SOPs/forms (category fixed). */
  defaultDocumentIds?: string[]
}

interface Values {
  category: TaskCategory
  study_id?: string
  subject_name?: string
  document_ids?: string[]
  title: string
  description?: string
  assignee_ids: string[]
  due_date?: Dayjs | null
  status?: TaskStatus
}

const TITLE_HINTS: Record<TaskCategory, string> = {
  study: 'e.g. Collect signed CVs for site 102',
  sop: 'e.g. Periodic review of CO-SOP-005',
  vendor: 'e.g. Annual requalification audit',
  system: 'e.g. Review user access list',
  general: 'e.g. Update the training matrix',
}

/** Form for creating, assigning and editing a task. People who may not assign a category to others
 * (e.g. a CRA) create tasks in it for themselves only. */
export function TaskFormModal({ open, onClose, task, defaultStudyId, planItem, defaultDocumentIds }: Props) {
  const linked = task?.plan_item ?? planItem ?? null
  const [form] = Form.useForm<Values>()
  const rights = useTaskRights()
  const creatable = rights.create
  const fixedCategory: TaskCategory | null = task
    ? task.category
    : defaultStudyId || planItem
      ? 'study'
      : defaultDocumentIds
        ? 'sop'
        : null
  const watched = Form.useWatch('category', form) as TaskCategory | undefined
  const category: TaskCategory = fixedCategory ?? watched ?? rights.assign[0] ?? creatable[0] ?? 'study'
  // Someone who may not assign this category to others creates (or edits) it for themselves only.
  const selfOnly = !rights.assign.includes(category)

  useEffect(() => {
    if (open && selfOnly && rights.meId) form.setFieldValue('assignee_ids', [rights.meId])
  }, [open, selfOnly, rights.meId, form])

  const studies = useStudies()
  const sops = useSops({}, { enabled: open && category === 'sop' })
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
    const named = category === 'vendor' || category === 'system'
    if (task) {
      update.mutate(
        {
          id: task.id,
          input: {
            title: v.title,
            description: v.description ?? null,
            ...(selfOnly ? {} : { assignee_ids: v.assignee_ids }),
            due_date: due,
            ...(named ? { subject_name: v.subject_name ?? null } : {}),
            ...(category === 'sop' ? { document_ids: v.document_ids ?? [] } : {}),
            // Only when changed: the status applies to everyone and would overwrite their own statuses.
            ...(v.status && v.status !== task.status ? { status: v.status } : {}),
          },
        },
        done,
      )
    } else {
      create.mutate(
        {
          category,
          ...(category === 'study'
            ? { study_id: v.study_id ?? null, plan_item_id: planItem?.external_id ?? null }
            : {}),
          ...(named ? { subject_name: v.subject_name ?? null } : {}),
          ...(category === 'sop' ? { document_ids: v.document_ids ?? [] } : {}),
          title: v.title,
          description: v.description ?? null,
          assignee_ids: selfOnly && rights.meId ? [rights.meId] : v.assignee_ids,
          due_date: due,
        },
        done,
      )
    }
  }

  const options = sopOptions(sops.data?.documents ?? [])
  // Keep SOPs already on the task selectable (and labelled) even if no longer in the approved list.
  for (const d of task?.documents ?? []) {
    if (!options.some((o) => o.value === d.sop_id)) {
      options.push({
        value: d.sop_id,
        label: `${d.sop_number ?? 'Unnumbered'}${d.version ? ` v${d.version}` : ''} · ${d.title} (no longer listed)`,
        kind: d.kind as 'sop' | 'form',
      })
    }
  }

  const categoryOptions = (fixedCategory ? [fixedCategory] : creatable).map((c) => ({
    value: c,
    label: TASK_CATEGORY_LABELS[c],
  }))

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
                category: task.category,
                study_id: task.study?.id,
                subject_name: task.subject_name ?? undefined,
                document_ids: task.documents.map((d) => d.sop_id),
                title: task.title,
                description: task.description ?? undefined,
                assignee_ids: task.assignees.map((a) => a.person_id),
                due_date: task.due_date ? dayjs(task.due_date) : null,
                status: task.status,
              }
            : {
                category,
                study_id: defaultStudyId,
                document_ids: defaultDocumentIds,
                title: planItem?.name,
              }
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
        <Form.Item name="category" label="Category" rules={[{ required: true, message: 'Choose a category' }]}>
          <Select
            aria-label="Category"
            disabled={editing || Boolean(fixedCategory) || categoryOptions.length < 2}
            options={categoryOptions}
          />
        </Form.Item>

        {category === 'study' && (
          <Form.Item name="study_id" label="Study" rules={[{ required: true, message: 'Choose a study' }]}>
            <Select
              aria-label="Study"
              disabled={editing}
              loading={studies.isLoading}
              placeholder="Choose a study"
              showSearch={{ optionFilterProp: 'label' }}
              options={(studies.data?.studies ?? []).map((s) => ({
                value: s.id,
                label: `${s.protocol_number} · ${s.title}`,
              }))}
            />
          </Form.Item>
        )}

        {category === 'sop' && (
          <Form.Item
            name="document_ids"
            label="SOPs and forms"
            extra="Approved documents only. The task records the version as it is today."
            rules={[{ required: true, type: 'array', min: 1, message: 'Choose at least one approved SOP or form' }]}
          >
            <Select
              aria-label="SOPs and forms"
              mode="multiple"
              loading={sops.isLoading}
              placeholder="Search by number or title"
              showSearch={{ optionFilterProp: 'label' }}
              maxCount={20}
              options={options}
              optionRender={(o) => (
                <span style={{ paddingLeft: o.data.kind === 'form' ? 16 : 0 }}>
                  {o.data.kind === 'form' && (
                    <Typography.Text type="secondary" style={{ marginRight: 6 }}>
                      Form
                    </Typography.Text>
                  )}
                  {o.label}
                </span>
              )}
            />
          </Form.Item>
        )}

        {(category === 'vendor' || category === 'system') && (
          <Form.Item
            name="subject_name"
            label={category === 'vendor' ? 'Vendor name' : 'Computer system'}
            rules={[{ required: true, whitespace: true, message: 'Enter the name' }]}
          >
            <Input maxLength={200} placeholder={category === 'vendor' ? 'e.g. Central lab name' : 'e.g. Viedoc'} />
          </Form.Item>
        )}

        <Form.Item
          name="title"
          label="Task"
          rules={[{ required: true, whitespace: true, min: 3, message: 'Describe the task (3+ characters)' }]}
        >
          <Input maxLength={300} placeholder={TITLE_HINTS[category]} />
        </Form.Item>
        <Form.Item
          name="description"
          label={category === 'sop' ? 'What to review (optional)' : 'Details (optional)'}
        >
          <Input.TextArea
            rows={3}
            maxLength={5000}
            placeholder={category === 'sop' ? 'e.g. Check section 6 against ICH E6(R3); confirm form CO-005-A still matches' : undefined}
          />
        </Form.Item>
        <Form.Item
          name="assignee_ids"
          label="Assign to"
          extra={
            selfOnly
              ? 'For your own tracking: you can create this kind of task for yourself only.'
              : 'Choose one or more people. Each person updates their own status; the task is completed when everyone has finished.'
          }
          rules={[{ required: true, type: 'array', min: 1, message: 'Choose at least one person' }]}
        >
          <Select
            aria-label="Assign to"
            mode="multiple"
            disabled={selfOnly}
            showSearch={{ optionFilterProp: 'label' }}
            loading={people.isLoading}
            placeholder="Choose people"
            maxCount={50}
            options={(people.data ?? []).map((p) => ({ value: p.id, label: `${p.name} (${p.job_title})` }))}
          />
        </Form.Item>
        <Form.Item name="due_date" label="Due date (optional)">
          <DatePicker format="DD MMM YYYY" style={{ width: '100%' }} />
        </Form.Item>
        {editing && (
          <Form.Item
            name="status"
            label={task && task.assignees.length > 1 ? 'Status (sets everyone)' : 'Status'}
            extra={task && task.assignees.length > 1 ? 'Leave as is to keep each person’s own status.' : undefined}
          >
            <Select options={TASK_STATUSES.map((s) => ({ value: s, label: s }))} />
          </Form.Item>
        )}
      </Form>
    </Modal>
  )
}
