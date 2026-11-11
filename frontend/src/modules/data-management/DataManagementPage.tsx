import { SyncOutlined } from '@ant-design/icons'
import { Alert, App, Button, Card, Empty, Flex, Result, Select, Skeleton, Tabs, Tag, Typography } from 'antd'
import { useEffect, useRef } from 'react'
import { useSearchParams } from 'react-router'

import { PageHeader } from '../../components/PageHeader'
import { formatDateTime } from '../../lib/format'
import type { DmConnection, DmStatus } from './api'
import { useDmOverview, useDmStatus, useDmSync } from './api'
import { OverviewTab } from './OverviewTab'
import { QueriesTab } from './QueriesTab'

const ENV_TAG: Record<string, { color: string; label: string }> = {
  demo: { color: 'gold', label: 'Demo study' },
  sandbox: { color: 'blue', label: 'Sandbox (test data)' },
  live: { color: 'red', label: 'Live study' },
}

function SourceBar({ status, connection }: { status: DmStatus; connection: DmConnection }) {
  const { message } = App.useApp()
  const sync = useDmSync()
  const overview = useDmOverview(connection.name)
  const env = ENV_TAG[connection.environment] ?? { color: 'default', label: connection.environment }
  const last = connection.last_run
  const asOf = overview.data?.as_of ?? connection.last_success_at
  return (
    <Card size="small" styles={{ body: { padding: '12px 16px' } }}>
      <Flex gap={12} wrap align="center">
        <Tag color={env.color} data-testid="dm-environment">
          {env.label}
        </Tag>
        <Typography.Text strong>{overview.data?.study_code ?? connection.name}</Typography.Text>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Source: Viedoc export (read-only copy) · {asOf ? `As of ${formatDateTime(asOf)}` : 'Not synced yet'}
          {status.sync_minutes > 0 ? ` · syncs every ${status.sync_minutes} minutes` : ''}
        </Typography.Text>
        {status.can_sync && (
          <Button
            icon={<SyncOutlined />}
            loading={sync.isPending}
            style={{ marginLeft: 'auto' }}
            onClick={() =>
              sync.mutate(connection.name, {
                onSuccess: (run) =>
                  run.ok
                    ? void message.success(`Synced: ${run.counts.queries ?? 0} queries`)
                    : void message.error(`Sync failed: ${run.error ?? 'unknown error'}`),
              })
            }
          >
            Sync now
          </Button>
        )}
      </Flex>
      {last && !last.ok && (
        <Alert
          type="error"
          showIcon
          style={{ marginTop: 10 }}
          title="The last sync failed; the previous copy is shown"
          description={last.error}
        />
      )}
    </Card>
  )
}

export function DataManagementPage() {
  const [params, setParams] = useSearchParams()
  const status = useDmStatus()
  // The newest address, updated on every change before React redraws, so two quick changes in a row
  // (e.g. a filter, then a checkbox) never undo each other.
  const latest = useRef(params)
  useEffect(() => {
    latest.current = params
  }, [params])

  const update = (changes: Record<string, string | undefined>) => {
    const next = new URLSearchParams(latest.current)
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value)
      else next.delete(key)
    }
    latest.current = next
    setParams(next, { replace: true })
  }

  if (status.isLoading) return <Skeleton active paragraph={{ rows: 8 }} />
  if (status.isError) return <Alert type="error" showIcon title="Could not load Data Management" description={status.error.message} />
  if (!status.data) {
    return (
      <Result
        status="info"
        title="Data Management is not available"
        subTitle="It is switched off, or your role does not include it. Ask an administrator."
      />
    )
  }
  const s = status.data
  const connection = s.connections.find((c) => c.name === params.get('connection')) ?? s.connections[0]
  if (!connection) return <Empty description="No Viedoc connection configured." />
  const tab = params.get('tab') === 'queries' ? 'queries' : 'overview'

  return (
    <>
      <PageHeader
        title="Data Management"
        subtitle="Viedoc queries and missing data: who is waiting on whom, and for how long."
      />
      <Flex vertical gap={16}>
        {s.connections.length > 1 && (
          <Select
            aria-label="Viedoc study"
            value={connection.name}
            onChange={(v: string) => update({ connection: v, site: undefined, form: undefined })}
            options={s.connections.map((c) => ({ value: c.name, label: `${c.name} (${c.environment})` }))}
            style={{ width: 280 }}
          />
        )}
        {s.demo && (
          <Alert
            type="warning"
            showIcon
            title="Demo data: no Viedoc study is connected"
            description="Add a Viedoc API connection in .env to see a real (sandbox) study."
          />
        )}
        <SourceBar status={s} connection={connection} />
        <Tabs
          activeKey={tab}
          onChange={(key) => update({ tab: key === 'overview' ? undefined : key })}
          items={[
            { key: 'overview', label: 'Overview', children: <OverviewTab connection={connection.name} status={s} onOpen={(f) => update({ tab: 'queries', ...f })} /> },
            {
              key: 'queries',
              label: 'Queries',
              children: (
                <QueriesTab
                  connection={connection.name}
                  status={s}
                  params={params}
                  onChange={(changes) => update(changes)}
                />
              ),
            },
          ]}
        />
      </Flex>
    </>
  )
}
