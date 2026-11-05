import { WarningOutlined } from '@ant-design/icons'
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Empty,
  Flex,
  Input,
  Row,
  Select,
  Statistic,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import type { TableColumnsType } from 'antd'
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router'

import { useRefreshSops, useSops } from '../../api/hooks'
import { SOP_STATUSES } from '../../api/types'
import type { SopDocument, SopFilters, SopStatus } from '../../api/types'
import { PageHeader } from '../../components/PageHeader'
import { SourceBanner } from '../../components/SourceBanner'
import { StatusTag } from '../../components/StatusTag'
import { formatDate } from '../../lib/format'
import { isReviewDue } from '../../lib/sops'

function readFilters(params: URLSearchParams): SopFilters {
  const status = params.get('status')
  return {
    q: params.get('q') ?? undefined,
    status: SOP_STATUSES.includes(status as SopStatus) ? (status as SopStatus) : undefined,
    department: params.get('department') ?? undefined,
  }
}

const columns: TableColumnsType<SopDocument> = [
  {
    title: 'SOP no.',
    dataIndex: 'sop_number',
    width: 120,
    render: (value: string | null, doc) => <Link to={`/documents/sops/${doc.id}`}>{value ?? '—'}</Link>,
  },
  {
    title: 'Title',
    dataIndex: 'title',
    render: (title: string, doc) => (
      <Link to={`/documents/sops/${doc.id}`} style={{ fontWeight: 500 }}>
        {title}
      </Link>
    ),
  },
  { title: 'Version', dataIndex: 'version', width: 90, render: (v: string | null) => v ?? '—' },
  {
    title: 'Status',
    dataIndex: 'status',
    width: 160,
    render: (_: SopStatus, doc) => <StatusTag status={doc.status} source={doc.status_source} />,
  },
  {
    title: 'Department',
    dataIndex: 'department',
    responsive: ['md'],
    render: (v: string | null) => v ?? '—',
  },
  {
    title: 'Effective',
    dataIndex: 'effective_date',
    width: 130,
    responsive: ['lg'],
    render: (v: string | null) => <span style={{ whiteSpace: 'nowrap' }}>{formatDate(v)}</span>,
  },
  {
    title: 'Next review',
    dataIndex: 'review_date',
    width: 180,
    responsive: ['lg'],
    render: (v: string | null, doc) => (
      <Flex gap={6} align="center" style={{ whiteSpace: 'nowrap' }}>
        {formatDate(v)}
        {isReviewDue(doc) && (
          <Tooltip title="Review date is past or within 30 days">
            <Tag color="warning" icon={<WarningOutlined />} style={{ marginInlineEnd: 0 }}>
              Due
            </Tag>
          </Tooltip>
        )}
      </Flex>
    ),
  },
]

export function SopListPage() {
  const [params, setParams] = useSearchParams()
  const filters = readFilters(params)
  const [searchText, setSearchText] = useState(filters.q ?? '')
  const [syncedQ, setSyncedQ] = useState(filters.q)
  const { data, isLoading, isError, error, refetch, isFetching } = useSops(filters)
  const refresh = useRefreshSops()
  const { message } = App.useApp()

  // Keep the search box in sync when the global search changes the URL
  // (adjusting state during render, as React recommends, instead of in an effect).
  if (syncedQ !== filters.q) {
    setSyncedQ(filters.q)
    setSearchText(filters.q ?? '')
  }

  const setFilter = (key: keyof SopFilters, value: string | undefined) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }

  const hasFilters = Boolean(filters.q || filters.status || filters.department)

  return (
    <>
      <PageHeader
        title="Documents and Knowledge"
        subtitle="Controlled documents from Avion SharePoint, kept in one place."
      />
      <Tabs
        activeKey="sops"
        items={[
          { key: 'sops', label: 'SOPs' },
          { key: 'templates', label: 'Templates (coming next)', disabled: true },
          { key: 'study', label: 'Study documents (coming next)', disabled: true },
        ]}
      />

      {isError && (
        <Alert
          type="error"
          showIcon
          style={{ marginBottom: 16 }}
          title="Could not load SOPs"
          description={error.message}
          action={<Button onClick={() => void refetch()}>Try again</Button>}
        />
      )}

      {data && (
        <SourceBanner
          source={data.source}
          fetchedAt={data.fetched_at}
          fromCache={data.from_cache}
          refreshing={refresh.isPending}
          onRefresh={() =>
            refresh.mutate(undefined, {
              onSuccess: () => void message.success('SOP list refreshed from SharePoint'),
              onError: (e) => void message.error(e.message),
            })
          }
        />
      )}

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        {[
          { label: 'SOPs in library', value: data?.summary.total },
          { label: 'Effective', value: data?.summary.effective },
          { label: 'In review or draft', value: data?.summary.in_review_or_draft },
          {
            label: 'Review due within 30 days',
            value: data?.summary.review_due,
            help: 'Effective SOPs whose review date is past or within the next 30 days.',
          },
        ].map((s) => (
          <Col key={s.label} xs={12} lg={6}>
            <Card size="small" loading={isLoading}>
              <Statistic
                title={s.help ? <Tooltip title={s.help}>{s.label}</Tooltip> : s.label}
                value={s.value ?? '—'}
              />
            </Card>
          </Col>
        ))}
      </Row>

      <Card>
        <Flex gap={12} wrap style={{ marginBottom: 16 }} role="search" aria-label="Filter SOPs">
          <Input.Search
            aria-label="Search SOPs"
            placeholder="Search number, title, department or owner"
            allowClear
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            onSearch={(v) => setFilter('q', v.trim() || undefined)}
            style={{ width: 340, maxWidth: '100%' }}
          />
          <Select
            aria-label="Filter by status"
            placeholder="All statuses"
            allowClear
            value={filters.status}
            onChange={(v?: SopStatus) => setFilter('status', v)}
            options={SOP_STATUSES.map((s) => ({ value: s, label: s }))}
            style={{ width: 180 }}
          />
          <Select
            aria-label="Filter by department"
            placeholder="All departments"
            allowClear
            value={filters.department}
            onChange={(v?: string) => setFilter('department', v)}
            options={(data?.departments ?? []).map((d) => ({ value: d, label: d }))}
            style={{ width: 220 }}
          />
          {hasFilters && (
            <Button onClick={() => setParams(new URLSearchParams(), { replace: true })}>
              Clear filters
            </Button>
          )}
        </Flex>

        <Table<SopDocument>
          rowKey="id"
          size="middle"
          columns={columns}
          dataSource={data?.documents ?? []}
          loading={isLoading || (isFetching && !data)}
          pagination={{ pageSize: 25, hideOnSinglePage: true, showSizeChanger: false }}
          locale={{
            emptyText: (
              <Empty
                description={
                  data && data.total_unfiltered === 0
                    ? 'No documents were found in the configured SharePoint library.'
                    : 'No SOPs match these filters.'
                }
              >
                {hasFilters && (
                  <Button onClick={() => setParams(new URLSearchParams(), { replace: true })}>
                    Clear filters
                  </Button>
                )}
              </Empty>
            ),
          }}
          summary={() =>
            data && hasFilters ? (
              <Table.Summary.Row>
                <Table.Summary.Cell index={0} colSpan={7}>
                  <Typography.Text type="secondary">
                    Showing {data.documents.length} of {data.total_unfiltered} SOPs
                  </Typography.Text>
                </Table.Summary.Cell>
              </Table.Summary.Row>
            ) : null
          }
        />
      </Card>
    </>
  )
}
