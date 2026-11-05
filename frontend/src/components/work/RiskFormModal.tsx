import { App, Form, Input, Modal, Radio, Select } from 'antd'

import { useCreateRisk, usePeople, useStudies, useUpdateRisk } from '../../api/hooks'
import { RISK_STATUSES } from '../../api/types'
import type { Risk, RiskKind, RiskStatus } from '../../api/types'
import { LEVELS } from '../../lib/studies'

interface Props {
  open: boolean
  onClose: () => void
  risk?: Risk | null
  defaultStudyId?: string
}

interface Values {
  study_id: string
  kind: RiskKind
  title: string
  description?: string
  likelihood: number
  impact: number
  mitigation?: string
  owner_id: string
  status?: RiskStatus
}

const LEVEL_OPTIONS = [1, 2, 3].map((n) => ({ value: n, label: LEVELS[n] }))

/** Administrator form for raising and editing a risk or issue. */
export function RiskFormModal({ open, onClose, risk, defaultStudyId }: Props) {
  const [form] = Form.useForm<Values>()
  const studies = useStudies()
  const people = usePeople()
  const create = useCreateRisk()
  const update = useUpdateRisk()
  const { message } = App.useApp()

  const submit = (v: Values) => {
    const input = {
      kind: v.kind,
      title: v.title,
      description: v.description ?? null,
      likelihood: v.likelihood,
      impact: v.impact,
      mitigation: v.mitigation ?? null,
      owner_id: v.owner_id,
    }
    const done = {
      onSuccess: () => {
        void message.success(risk ? 'Saved' : v.kind === 'risk' ? 'Risk raised' : 'Issue raised')
        onClose()
      },
      onError: (e: Error) => void message.error(e.message),
    }
    if (risk) update.mutate({ id: risk.id, input: { ...input, ...(v.status ? { status: v.status } : {}) } }, done)
    else create.mutate({ ...input, study_id: v.study_id }, done)
  }

  return (
    <Modal
      open={open}
      title={risk ? `Edit ${risk.reference}` : 'Raise a risk or issue'}
      okText={risk ? 'Save changes' : 'Raise'}
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
          risk
            ? {
                study_id: risk.study.id,
                kind: risk.kind,
                title: risk.title,
                description: risk.description ?? undefined,
                likelihood: risk.likelihood,
                impact: risk.impact,
                mitigation: risk.mitigation ?? undefined,
                owner_id: risk.owner_id,
                status: risk.status,
              }
            : { study_id: defaultStudyId, kind: 'risk', likelihood: 2, impact: 2 }
        }
      >
        <Form.Item name="study_id" label="Study" rules={[{ required: true, message: 'Choose a study' }]}>
          <Select
            disabled={Boolean(risk)}
            loading={studies.isLoading}
            placeholder="Choose a study"
            options={(studies.data?.studies ?? []).map((s) => ({
              value: s.id,
              label: `${s.protocol_number} · ${s.title}`,
            }))}
          />
        </Form.Item>
        <Form.Item name="kind" label="Type">
          <Radio.Group
            optionType="button"
            options={[
              { value: 'risk', label: 'Risk (may happen)' },
              { value: 'issue', label: 'Issue (has happened)' },
            ]}
          />
        </Form.Item>
        <Form.Item
          name="title"
          label="Description"
          rules={[{ required: true, whitespace: true, min: 3, message: 'Describe the risk (3+ characters)' }]}
        >
          <Input maxLength={300} />
        </Form.Item>
        <Form.Item name="description" label="Details (optional)">
          <Input.TextArea rows={2} maxLength={5000} />
        </Form.Item>
        <Form.Item name="likelihood" label="Likelihood">
          <Radio.Group optionType="button" options={LEVEL_OPTIONS} />
        </Form.Item>
        <Form.Item name="impact" label="Impact">
          <Radio.Group optionType="button" options={LEVEL_OPTIONS} />
        </Form.Item>
        <Form.Item name="mitigation" label="Mitigation / action (optional)">
          <Input.TextArea rows={2} maxLength={5000} />
        </Form.Item>
        <Form.Item name="owner_id" label="Owner" rules={[{ required: true, message: 'Choose an owner' }]}>
          <Select
            showSearch={{ optionFilterProp: 'label' }}
            loading={people.isLoading}
            placeholder="Choose a person"
            options={(people.data ?? []).map((p) => ({ value: p.id, label: `${p.name} (${p.job_title})` }))}
          />
        </Form.Item>
        {risk && (
          <Form.Item name="status" label="Status">
            <Select options={RISK_STATUSES.map((s) => ({ value: s, label: s }))} />
          </Form.Item>
        )}
      </Form>
    </Modal>
  )
}
