import { EditOutlined, LockOutlined } from '@ant-design/icons'
import { App, Button, Empty, Select, Table, Tooltip, Typography } from 'antd'
import type { TableColumnsType } from 'antd'
import { Link } from 'react-router'

import { useRiskStatus } from '../../api/hooks'
import { RISK_STATUSES } from '../../api/types'
import type { Risk, RiskStatus } from '../../api/types'
import { LEVELS, RISK_RATING_STYLE, RISK_STATUS_STYLE } from '../../lib/studies'
import { ToneTag } from '../ToneTag'

interface Props {
  risks: Risk[]
  loading?: boolean
  canManage: boolean
  showStudy?: boolean
  onEdit?: (risk: Risk) => void
  emptyText: string
  scoreRule?: string
}

function StatusCell({ risk }: { risk: Risk }) {
  const change = useRiskStatus()
  const { message } = App.useApp()
  if (!risk.can_update_status) {
    return (
      <Tooltip title="Only the owner of this risk or issue can update its status.">
        <span style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>
          <ToneTag tone={RISK_STATUS_STYLE[risk.status]} />
          <LockOutlined aria-label="Read-only" style={{ color: '#5B6B82' }} />
        </span>
      </Tooltip>
    )
  }
  return (
    <Select<RiskStatus>
      size="small"
      aria-label={`Status of ${risk.reference}`}
      value={risk.status}
      disabled={change.isPending}
      style={{ width: 130 }}
      onChange={(status) =>
        // mutateAsync so the confirmation survives the row leaving the list (e.g. when closed).
        void change
          .mutateAsync({ id: risk.id, status })
          .then(() => message.success(`${risk.reference} marked ${status}`))
          .catch((e: Error) => message.error(e.message))
      }
      options={RISK_STATUSES.map((s) => ({ value: s, label: s }))}
    />
  )
}

export function RiskTable({ risks, loading, canManage, showStudy = false, onEdit, emptyText, scoreRule }: Props) {
  const columns: TableColumnsType<Risk> = [
    {
      title: 'Ref.',
      dataIndex: 'reference',
      width: 100,
      render: (ref: string, r) => (
        <div>
          <div>{ref}</div>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {r.kind === 'risk' ? 'Risk' : 'Issue'}
          </Typography.Text>
        </div>
      ),
    },
    {
      title: 'Description',
      dataIndex: 'title',
      render: (title: string, r) => (
        <div>
          <Typography.Text strong>{title}</Typography.Text>
          {r.mitigation && (
            <Typography.Paragraph type="secondary" ellipsis={{ rows: 2 }} style={{ margin: 0, fontSize: 13 }}>
              Mitigation: {r.mitigation}
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
            render: (_: unknown, r: Risk) => (
              <Link to={`/command-centre/${r.study.id}`}>{r.study.protocol_number}</Link>
            ),
          },
        ]
      : []),
    {
      title: 'Score',
      dataIndex: 'score',
      width: 150,
      render: (score: number, r) => (
        <ToneTag
          tone={RISK_RATING_STYLE[r.rating]}
          help={`Likelihood ${LEVELS[r.likelihood]} × impact ${LEVELS[r.impact]} = ${score}. ${scoreRule ?? ''}`}
        >
          {r.rating} ({score})
        </ToneTag>
      ),
    },
    { title: 'Owner', dataIndex: 'owner_name', width: 160, responsive: ['md'] },
    {
      title: 'Status',
      dataIndex: 'status',
      width: 160,
      render: (_: RiskStatus, r) => <StatusCell risk={r} />,
    },
    ...(canManage && onEdit
      ? [
          {
            title: <span className="sr-only">Actions</span>,
            key: 'actions',
            width: 60,
            render: (_: unknown, r: Risk) => (
              <Button type="text" icon={<EditOutlined />} aria-label={`Edit ${r.reference}`} onClick={() => onEdit(r)} />
            ),
          },
        ]
      : []),
  ]

  return (
    <Table<Risk>
      rowKey="id"
      size="middle"
      columns={columns}
      dataSource={risks}
      loading={loading}
      pagination={{ pageSize: 20, hideOnSinglePage: true, showSizeChanger: false }}
      locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={emptyText} /> }}
    />
  )
}
