import { Card, Table, Tag, Typography } from 'antd'
import { useState } from 'react'

import { useAuditEvents, useHasPermission, useMe } from '../../api/hooks'
import type { AuditEvent } from '../../api/types'
import { Forbidden } from '../../components/Forbidden'
import { PageHeader } from '../../components/PageHeader'
import { formatDateTime } from '../../lib/format'

const PAGE_SIZE = 25

export function AuditTrailPage() {
  const me = useMe()
  const allowed = useHasPermission('audit.read')
  const [page, setPage] = useState(1)
  const { data, isLoading } = useAuditEvents((page - 1) * PAGE_SIZE, PAGE_SIZE, allowed)

  if (me.isSuccess && !allowed) return <Forbidden what="the audit trail" />

  return (
    <>
      <PageHeader
        title="Audit Trail"
        subtitle="Append-only record of actions taken in Avi.Intelligence."
      />
      <Card>
        <Table<AuditEvent>
          rowKey="id"
          loading={isLoading}
          dataSource={data?.items ?? []}
          pagination={{
            current: page,
            pageSize: PAGE_SIZE,
            total: data?.total ?? 0,
            onChange: setPage,
            showSizeChanger: false,
            hideOnSinglePage: true,
          }}
          locale={{ emptyText: 'No audit events recorded yet.' }}
          columns={[
            {
              title: 'When',
              dataIndex: 'occurred_at',
              width: 190,
              render: (v: string) => formatDateTime(v),
            },
            {
              title: 'User',
              dataIndex: 'actor_name',
              render: (name: string, e) => (
                <>
                  {name}
                  <br />
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {e.actor_role}
                  </Typography.Text>
                </>
              ),
            },
            { title: 'Action', dataIndex: 'action', width: 180, render: (a: string) => <Tag>{a}</Tag> },
            { title: 'Details', dataIndex: 'summary' },
          ]}
        />
      </Card>
    </>
  )
}
