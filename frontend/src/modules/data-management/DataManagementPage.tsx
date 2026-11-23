import { SyncOutlined } from '@ant-design/icons'
import { Alert, App, Button, Card, Empty, Flex, Result, Select, Skeleton, Tabs, Tag, Typography } from 'antd'
import { useEffect, useRef } from 'react'
import { useSearchParams } from 'react-router'

import { PageHeader } from '../../components/PageHeader'
import { formatDateTime } from '../../lib/format'
import type { DmScope, DmStatus } from './api'
import { useDmOverview, useDmStatus, useDmSync } from './api'
import { OverviewTab } from './OverviewTab'
import { LabsTab } from './LabsTab'
import { MissingTab } from './MissingTab'
import { QueriesTab } from './QueriesTab'
import { SdvTab } from './SdvTab'

const ENV_TAG: Record<string, { color: string; label: string }> = {
  demo: { color: 'gold', label: 'Demo study' },
  sandbox: { color: 'blue', label: 'Sandbox (test data)' },
  live: { color: 'red', label: 'Live study' },
}

function SourceBar({ status, scope }: { status: DmStatus; scope: DmScope }) {
  const { message } = App.useApp()
  const sync = useDmSync()
  const overview = useDmOverview(scope.id)
  const env = ENV_TAG[scope.environment] ?? { color: 'default', label: scope.environment }
  // The studies in view: for "All sandbox/live studies", every study of that environment.
  const names = scope.multi
    ? status.connections.filter((c) => c.environment === scope.environment).map((c) => c.name)
    : [scope.id]
  const failed = status.connections.filter((c) => names.includes(c.name) && c.last_run && !c.last_run.ok)
  const asOf = overview.data?.as_of
  return (
    <Card size="small" styles={{ body: { padding: '12px 16px' } }}>
      <Flex gap={12} wrap align="center">
        <Tag color={env.color} data-testid="dm-environment">
          {env.label}
        </Tag>
        <Typography.Text strong data-testid="dm-scope-title">
          {scope.multi ? `${scope.label} (${names.length})` : (overview.data?.study_code ?? scope.label)}
        </Typography.Text>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Source: Viedoc export (read-only copy) · {asOf ? `As of ${formatDateTime(asOf)}` : 'Not synced yet'}
          {status.sync_minutes > 0 ? ` · syncs every ${status.sync_minutes} minutes` : ''}
        </Typography.Text>
        {status.can_sync && (
          <Button
            icon={<SyncOutlined />}
            loading={sync.isPending}
            style={{ marginLeft: 'auto' }}
            disabled={names.length === 0}
            onClick={() =>
              sync.mutate(names, {
                onSuccess: (runs) => {
                  const bad = runs.filter((r) => !r.ok)
                  const total = runs.reduce((n, r) => n + Number(r.counts.queries ?? 0), 0)
                  if (bad.length) void message.error(`Sync failed for ${bad.length} of ${runs.length}: ${bad[0]?.error ?? ''}`)
                  else void message.success(`Synced: ${total} queries${runs.length > 1 ? ` from ${runs.length} studies` : ''}`)
                },
              })
            }
          >
            {scope.multi ? 'Sync all' : 'Sync now'}
          </Button>
        )}
      </Flex>
      {failed.map((c) => (
        <Alert
          key={c.name}
          type="error"
          showIcon
          style={{ marginTop: 10 }}
          title={`The last sync of ${c.study_code ?? c.name} failed; the previous copy is shown`}
          description={c.last_run?.error}
        />
      ))}
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
  const scope = s.scopes.find((c) => c.id === params.get('scope')) ?? s.scopes.find((c) => c.id === s.default_scope)
  if (!scope) return <Empty description="No Viedoc connection configured." />
  const raw = params.get('tab')
  const tab = raw === 'queries' || raw === 'sdv' || raw === 'missing' || raw === 'labs' ? raw : 'overview'

  return (
    <>
      <PageHeader
        title="Data Management"
        subtitle="Viedoc queries and missing data: who is waiting on whom, and for how long."
      />
      <Flex vertical gap={16}>
        <Flex gap={8} align="center" wrap>
          <label htmlFor="dm-study" style={{ fontWeight: 600 }}>
            Study
          </label>
          <Select
            id="dm-study"
            aria-label="Study"
            value={scope.id}
            onChange={(v: string) => update({ scope: v, site: undefined, form: undefined, study: undefined })}
            options={s.scopes.map((c) => ({ value: c.id, label: c.label }))}
            style={{ width: 320, maxWidth: '100%' }}
            popupMatchSelectWidth={false}
          />
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Live and sandbox studies are never combined.
          </Typography.Text>
        </Flex>
        {s.demo && (
          <Alert
            type="warning"
            showIcon
            title="Demo data: no Viedoc study is connected"
            description="Add a Viedoc API connection in .env to see a real (sandbox) study."
          />
        )}
        <SourceBar status={s} scope={scope} />
        <Tabs
          activeKey={tab}
          onChange={(key) => update({ tab: key === 'overview' ? undefined : key })}
          items={[
            {
              key: 'overview',
              label: 'Overview',
              children: (
                <OverviewTab
                  scope={scope.id}
                  status={s}
                  onOpen={(f) => update({ tab: 'queries', ...f })}
                  onOpenSdv={(site) => update({ tab: 'sdv', ssite: site })}
                />
              ),
            },
            {
              key: 'queries',
              label: 'Queries',
              children: (
                <QueriesTab
                  scope={scope.id}
                  status={s}
                  params={params}
                  onChange={(changes) => update(changes)}
                />
              ),
            },
            {
              key: 'sdv',
              label: 'SDV',
              children: (
                <SdvTab scope={scope.id} canExport={s.can_export} params={params} onChange={(changes) => update(changes)} />
              ),
            },
            {
              key: 'missing',
              label: 'Missing data',
              children: (
                <MissingTab scope={scope.id} canExport={s.can_export} params={params} onChange={(changes) => update(changes)} />
              ),
            },
            {
              key: 'labs',
              label: 'Labs',
              children: (
                <LabsTab scope={scope.id} canExport={s.can_export} params={params} onChange={(changes) => update(changes)} />
              ),
            },
          ]}
        />
      </Flex>
    </>
  )
}
