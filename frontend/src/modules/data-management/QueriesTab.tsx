import { Alert, Checkbox, Descriptions, Drawer, Flex, Input, Select, Skeleton, Table, Tag, Timeline, Typography } from 'antd'
import { useState } from 'react'

import { formatDateTime } from '../../lib/format'
import { TONES } from '../../lib/studies'
import type { DmFlag, DmQuery, DmQueryFilters, DmState, DmStatus } from './api'
import { useDmOverview, useDmQueries, useDmQuery } from './api'

interface Props {
  connection: string
  status: DmStatus
  params: URLSearchParams
  onChange: (changes: Record<string, string | undefined>) => void
}

const STATE_TONE: Record<DmState, keyof typeof TONES> = { open_at_site: 'info', awaiting_approval: 'warn', closed: 'good' }
const FLAG: Record<DmFlag, { color: string; label: string }> = {
  red: { color: '#B42318', label: 'Over target' },
  amber: { color: '#B26B00', label: 'Last day of target' },
  green: { color: '#1E7F4F', label: 'Within target' },
  none: { color: '#C9D1DC', label: 'Closed' },
}

function StateTag({ q }: { q: DmQuery }) {
  const t = TONES[STATE_TONE[q.state]]
  return (
    <Tag style={{ color: t.color, background: t.background, borderColor: t.border, marginInlineEnd: 0 }}>{q.state_label}</Tag>
  )
}

function Clock({ q, status }: { q: DmQuery; status: DmStatus }) {
  if (q.state === 'closed') return <Typography.Text type="secondary">—</Typography.Text>
  const who = q.state === 'open_at_site' ? 'Site' : 'Us'
  const target = q.state === 'open_at_site' ? status.site_answer_days : status.approval_days
  const f = FLAG[q.flag]
  return (
    <Flex align="center" gap={6} title={`${f.label}: ${q.clock_days ?? 0} of ${target} working days`}>
      <span aria-hidden style={{ width: 10, height: 10, borderRadius: '50%', background: f.color, flexShrink: 0 }} />
      <span>
        {who}: <strong>{q.clock_days ?? 0}</strong> / {target} wd
      </span>
      <span className="sr-only">{f.label}</span>
    </Flex>
  )
}

function QueryDrawer({ id, onClose }: { id: string | null; onClose: () => void }) {
  const { data, isLoading } = useDmQuery(id)
  return (
    <Drawer open={Boolean(id)} onClose={onClose} width={560} title={data ? `Query ${data.query_number}` : 'Query'}>
      {isLoading || !data ? (
        <Skeleton active />
      ) : (
        <Flex vertical gap={16}>
          <Descriptions size="small" column={1} bordered>
            <Descriptions.Item label="Site">{data.site_code} · {data.site_name}</Descriptions.Item>
            <Descriptions.Item label="Subject">{data.subject_id}</Descriptions.Item>
            <Descriptions.Item label="Visit">{data.event_name ?? '—'}</Descriptions.Item>
            <Descriptions.Item label="Form · field">
              {data.form_name ?? data.form_id ?? '—'} · {data.item_label ?? data.item_id ?? '—'}
            </Descriptions.Item>
            <Descriptions.Item label="Type">
              {data.query_type}
              {data.edit_check ? ` · check ${data.edit_check}` : ''}
            </Descriptions.Item>
            <Descriptions.Item label="Query">{data.query_text ?? '—'}</Descriptions.Item>
            <Descriptions.Item label="State">
              <StateTag q={data} /> <Typography.Text type="secondary">(Viedoc: {data.viedoc_state})</Typography.Text>
            </Descriptions.Item>
            {data.reopen_count > 0 && <Descriptions.Item label="Sent back">{data.reopen_count} time(s)</Descriptions.Item>}
          </Descriptions>
          <div>
            <Typography.Title level={5}>History</Typography.Title>
            <Timeline
              items={data.events.map((e) => ({
                key: `${e.viedoc_state}-${e.at}`,
                children: (
                  <Flex vertical>
                    <strong>{e.viedoc_state}</strong>
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      {e.at ? formatDateTime(e.at) : 'No date'} · {e.user_role ?? 'System'}
                      {e.user_name ? ` (${e.user_name})` : ''}
                    </Typography.Text>
                    {e.resolution && <span style={{ fontSize: 13 }}>{e.resolution}</span>}
                  </Flex>
                ),
              }))}
            />
          </div>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Read-only copy: answer and approve queries in Viedoc. Changes appear after the next sync.
          </Typography.Text>
        </Flex>
      )}
    </Drawer>
  )
}

export function QueriesTab({ connection, status, params, onChange }: Props) {
  const [openId, setOpenId] = useState<string | null>(null)
  const filters: DmQueryFilters = {
    connection,
    state: (params.get('state') as DmQueryFilters['state']) ?? 'not_closed',
    site: params.get('site') ?? undefined,
    form: params.get('form') ?? undefined,
    flag: (params.get('flag') as DmQueryFilters['flag']) ?? undefined,
    reopened: params.get('reopened') === 'true',
    search: params.get('q') ?? undefined,
  }
  const overview = useDmOverview(connection)
  const { data, isLoading, isError, error } = useDmQueries(filters)

  return (
    <Flex vertical gap={12}>
      <Flex gap={10} wrap align="center">
        <Select
          aria-label="Query state"
          value={filters.state}
          onChange={(v: string) => onChange({ state: v === 'not_closed' ? undefined : v })}
          style={{ width: 220 }}
          options={[
            { value: 'not_closed', label: 'Not closed (open or awaiting)' },
            { value: 'open_at_site', label: 'Open at site' },
            { value: 'awaiting_approval', label: 'Answered, awaiting approval' },
            { value: 'closed', label: 'Closed' },
          ]}
        />
        <Select
          aria-label="Site"
          allowClear
          placeholder="All sites"
          value={filters.site}
          onChange={(v?: string) => onChange({ site: v })}
          style={{ width: 220 }}
          options={(overview.data?.site_options ?? []).map((o) => ({ value: o.id, label: o.label }))}
        />
        <Select
          aria-label="Form"
          allowClear
          placeholder="All forms"
          value={filters.form}
          onChange={(v?: string) => onChange({ form: v })}
          style={{ width: 200 }}
          options={(overview.data?.form_options ?? []).map((o) => ({ value: o.id, label: o.label }))}
        />
        <Select
          aria-label="Target"
          allowClear
          placeholder="Any target status"
          value={filters.flag}
          onChange={(v?: string) => onChange({ flag: v })}
          style={{ width: 180 }}
          options={[
            { value: 'red', label: 'Over target' },
            { value: 'amber', label: 'Last day of target' },
            { value: 'green', label: 'Within target' },
          ]}
        />
        <Checkbox checked={filters.reopened} onChange={(e) => onChange({ reopened: e.target.checked ? 'true' : undefined })}>
          Sent back at least once
        </Checkbox>
        <Input.Search
          aria-label="Search queries"
          placeholder="Subject, query no., field, check"
          allowClear
          defaultValue={filters.search}
          onSearch={(v) => onChange({ q: v || undefined })}
          style={{ width: 260 }}
        />
      </Flex>
      {isError && <Alert type="error" showIcon title="Could not load queries" description={error.message} />}
      {isLoading || !data ? (
        <Skeleton active paragraph={{ rows: 8 }} />
      ) : (
        <>
          <Typography.Text type="secondary" data-testid="dm-query-count">
            {data.total} quer{data.total === 1 ? 'y' : 'ies'} · worst first (over target, then longest waiting)
          </Typography.Text>
          <Table<DmQuery>
            size="small"
            rowKey="id"
            dataSource={data.queries}
            pagination={data.queries.length > 50 ? { pageSize: 50, showSizeChanger: false } : false}
            scroll={{ x: 1000 }}
            onRow={(r) =>
              ({
                'data-testid': 'dm-query-row',
                onClick: () => setOpenId(r.id),
                style: { cursor: 'pointer' },
              }) as React.HTMLAttributes<HTMLElement>
            }
            columns={[
              { title: 'Clock', key: 'clock', width: 170, render: (_, r) => <Clock q={r} status={status} /> },
              { title: 'No.', dataIndex: 'query_number', width: 60 },
              { title: 'Site', dataIndex: 'site_code', width: 70 },
              { title: 'Subject', dataIndex: 'subject_id', width: 100 },
              { title: 'Visit', dataIndex: 'event_name', render: (v: string | null) => v ?? '—' },
              {
                title: 'Form · field',
                key: 'item',
                render: (_, r) => (
                  <span>
                    {r.form_name ?? r.form_id ?? '—'} · <Typography.Text type="secondary">{r.item_label ?? '—'}</Typography.Text>
                  </span>
                ),
              },
              { title: 'State', key: 'state', render: (_, r) => <StateTag q={r} /> },
              { title: 'Age (days)', dataIndex: 'age_days', align: 'right', width: 90, render: (v: number | null) => v ?? '—' },
              {
                title: 'Sent back',
                dataIndex: 'reopen_count',
                align: 'right',
                width: 90,
                render: (v: number) => (v ? <Tag color="orange">{v}×</Tag> : ''),
              },
            ]}
          />
        </>
      )}
      <QueryDrawer id={openId} onClose={() => setOpenId(null)} />
    </Flex>
  )
}
