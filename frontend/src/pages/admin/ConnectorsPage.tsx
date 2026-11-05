import { CheckCircleFilled, CloseCircleFilled, ReloadOutlined, SyncOutlined } from '@ant-design/icons'
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Flex,
  Row,
  Skeleton,
  Table,
  Tag,
  Typography,
} from 'antd'

import {
  useHasPermission,
  useMe,
  useSharePointStatus,
  useSimpleTrialsStatus,
  useSyncSimpleTrials,
} from '../../api/hooks'
import type { ConnectorColumn } from '../../api/types'
import { formatDateTime } from '../../lib/format'
import { Forbidden } from '../../components/Forbidden'
import { PageHeader } from '../../components/PageHeader'
import { AssistantAdminCard } from './AssistantAdminCard'

const FIELD_LABELS: Record<string, string> = {
  sop_number: 'SOP number',
  title: 'Title',
  version: 'Version',
  status: 'Status',
  effective_date: 'Effective date',
  review_date: 'Review date',
  owner: 'Owner',
  department: 'Department',
}

const PLANNED = ['Avie Safety database', 'Viedoc', 'Medidata Rave', 'Email (Microsoft 365)']

function SimpleTrialsCard({ enabled }: { enabled: boolean }) {
  const { data, isLoading } = useSimpleTrialsStatus(enabled)
  const sync = useSyncSimpleTrials()
  const last = data?.last_sync
  return (
    <Card
      title="SimpleTrials: studies, sites and milestones"
      style={{ marginTop: 16 }}
      extra={
        data && (
          <Tag color={data.connector.mode === 'mock' ? 'warning' : last?.ok ? 'success' : 'error'}>
            {data.connector.mode === 'mock' ? 'Demo mode' : last?.ok ? 'Connected' : 'Sync problem'}
          </Tag>
        )
      }
    >
      {isLoading || !data ? (
        <Skeleton active />
      ) : (
        <Flex vertical gap={12}>
          {data.connector.mock_reason && (
            <Typography.Text type="secondary">{data.connector.mock_reason}</Typography.Text>
          )}
          <Descriptions
            column={1}
            size="small"
            items={[
              { key: 'mode', label: 'Mode', children: data.connector.mode },
              {
                key: 'last',
                label: 'Last sync',
                children: last
                  ? `${formatDateTime(last.finished_at ?? last.started_at)} · ${last.ok ? 'succeeded' : 'failed'} · by ${last.triggered_by}`
                  : 'Never',
              },
              {
                key: 'counts',
                label: 'Result',
                children: last?.ok
                  ? `${last.counts.studies ?? 0} studies (${last.counts.created ?? 0} new, ${last.counts.updated ?? 0} updated, ${last.counts.no_longer_in_source ?? 0} no longer in source)`
                  : (last?.error ?? '—'),
              },
            ]}
          />
          <div>
            <Button icon={<SyncOutlined />} loading={sync.isPending} onClick={() => sync.mutate()}>
              Sync now
            </Button>
          </div>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Next: import SimpleTrials export files, then the SimpleTrials API if available. See
            docs/simpletrials-setup.md.
          </Typography.Text>
        </Flex>
      )}
    </Card>
  )
}

export function ConnectorsPage() {
  const me = useMe()
  const allowed = useHasPermission('connector.manage')
  const { data, isLoading, isFetching, isError, error, refetch } = useSharePointStatus(allowed)

  if (me.isSuccess && !allowed) return <Forbidden what="connector settings" />

  const columnNames = new Set((data?.check.columns ?? []).map((c) => c.name))

  return (
    <>
      <PageHeader
        title="Administration"
        subtitle="Connections to Avion systems."
        breadcrumbs={[{ title: 'Administration' }, { title: 'Connectors' }]}
        extra={
          <Button icon={<ReloadOutlined />} onClick={() => void refetch()} loading={isFetching}>
            Re-run connection test
          </Button>
        }
      />

      {isError && <Alert type="error" showIcon title="Connection test failed to run" description={error.message} />}

      <Card
        title="SharePoint: SOP library"
        extra={
          data && (
            <Tag color={data.info.mode === 'live' ? (data.check.ok ? 'success' : 'error') : 'warning'}>
              {data.info.mode === 'live' ? (data.check.ok ? 'Connected' : 'Connection problem') : 'Demo mode'}
            </Tag>
          )
        }
      >
        {isLoading || !data ? (
          <Skeleton active />
        ) : (
          <Row gutter={[24, 24]}>
            <Col xs={24} lg={10}>
              <Descriptions
                column={1}
                size="small"
                items={[
                  { key: 'site', label: 'Site', children: data.info.site_url ?? 'Not configured' },
                  { key: 'lib', label: 'Library', children: data.info.library },
                  { key: 'folder', label: 'Folder', children: data.info.folder ?? '(whole library)' },
                  {
                    key: 'count',
                    label: 'Documents found',
                    children: data.check.document_count ?? '—',
                  },
                ]}
              />
              <Typography.Title level={5} style={{ marginTop: 16 }}>
                Connection test
              </Typography.Title>
              <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
                {data.check.steps.map((step) => (
                  <li key={step.label} style={{ padding: '8px 0', borderBottom: '1px solid #EEF1F6' }}>
                    <Flex gap={8} align="flex-start">
                      {step.ok ? (
                        <CheckCircleFilled style={{ color: '#1E7F4F', marginTop: 4 }} aria-label="Passed" />
                      ) : (
                        <CloseCircleFilled style={{ color: '#B42318', marginTop: 4 }} aria-label="Failed" />
                      )}
                      <div>
                        <div>{step.label}</div>
                        {step.detail && (
                          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                            {step.detail}
                          </Typography.Text>
                        )}
                      </div>
                    </Flex>
                  </li>
                ))}
              </ul>
            </Col>
            <Col xs={24} lg={14}>
              <Typography.Title level={5} style={{ marginTop: 0 }}>
                Field mapping
              </Typography.Title>
              <Typography.Paragraph type="secondary">
                Each SOP field is read from the first matching SharePoint column. Change this with{' '}
                <Typography.Text code>SHAREPOINT_SOP_FIELD_MAP</Typography.Text>.
              </Typography.Paragraph>
              <Table
                size="small"
                pagination={false}
                rowKey="field"
                dataSource={Object.entries(data.info.field_map).map(([field, names]) => ({ field, names }))}
                columns={[
                  { title: 'SOP field', dataIndex: 'field', render: (f: string) => FIELD_LABELS[f] ?? f },
                  {
                    title: 'SharePoint columns tried (in order)',
                    dataIndex: 'names',
                    render: (names: string[]) => (
                      <Flex gap={4} wrap>
                        {names.map((n) => (
                          <Tag key={n} color={columnNames.has(n) ? 'blue' : undefined}>
                            {n}
                            {columnNames.has(n) ? ' ✓' : ''}
                          </Tag>
                        ))}
                      </Flex>
                    ),
                  },
                ]}
              />
              {data.check.columns && (
                <>
                  <Typography.Title level={5} style={{ marginTop: 16 }}>
                    Columns in this library
                  </Typography.Title>
                  <Table<ConnectorColumn>
                    size="small"
                    rowKey="name"
                    pagination={{ pageSize: 10, hideOnSinglePage: true }}
                    dataSource={data.check.columns}
                    columns={[
                      { title: 'Display name', dataIndex: 'display_name' },
                      {
                        title: 'Internal name',
                        dataIndex: 'name',
                        render: (n: string) => <Typography.Text code copyable>{n}</Typography.Text>,
                      },
                      { title: 'Type', dataIndex: 'type' },
                    ]}
                  />
                </>
              )}
            </Col>
          </Row>
        )}
      </Card>

      <SimpleTrialsCard enabled={allowed} />

      <AssistantAdminCard />

      <Card title="Planned connectors" style={{ marginTop: 16 }}>
        <Flex gap={8} wrap>
          {PLANNED.map((p) => (
            <Tag key={p}>{p}: not connected</Tag>
          ))}
        </Flex>
      </Card>
    </>
  )
}
