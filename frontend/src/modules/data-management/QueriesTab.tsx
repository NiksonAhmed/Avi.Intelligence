import { FilterOutlined } from '@ant-design/icons'
import { Alert, Badge, Button, DatePicker, Descriptions, Drawer, Flex, Input, Popover, Segmented, Select, Skeleton, Table, Tag, Timeline, Typography } from 'antd'
import dayjs from 'dayjs'
import { useState } from 'react'

import { formatDateTime, formatDay } from '../../lib/format'
import { TONES } from '../../lib/studies'
import type { DmFlag, DmQuery, DmQueryFilters, DmState, DmStatus } from './api'
import { useDmOverview, useDmQueries, useDmQuery } from './api'

interface Props {
  scope: string
  status: DmStatus
  params: URLSearchParams
  onChange: (changes: Record<string, string | undefined>) => void
}

const STATE_TONE: Record<DmState, keyof typeof TONES> = { open_at_site: 'info', awaiting_approval: 'warn', closed: 'good' }
const FLAG: Record<DmFlag, { color: string; label: string }> = {
  red: { color: '#B42318', label: 'Overdue' },
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
              {data.form_label}
              {data.item_label || data.item_id ? ` · ${data.item_label ?? data.item_id}` : ''}
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

type View = 'attention' | 'open' | 'awaiting' | 'overdue' | 'sent_back' | 'closed'

/** One click answers the usual questions; each view is a fixed combination of state, target and re-opens. */
const VIEWS: { key: View; label: string; filters: Pick<DmQueryFilters, 'state' | 'flag' | 'reopened'> }[] = [
  { key: 'attention', label: 'Needs attention', filters: { state: 'not_closed' } },
  { key: 'open', label: 'Open at site', filters: { state: 'open_at_site' } },
  { key: 'awaiting', label: 'Awaiting approval', filters: { state: 'awaiting_approval' } },
  { key: 'overdue', label: 'Overdue', filters: { state: 'not_closed', flag: 'red' } },
  { key: 'sent_back', label: 'Sent back', filters: { reopened: true } },
  { key: 'closed', label: 'Closed', filters: { state: 'closed' } },
]

export function QueriesTab({ scope, status, params, onChange }: Props) {
  const [openId, setOpenId] = useState<string | null>(null)
  const view = VIEWS.find((v) => v.key === params.get('view')) ?? VIEWS[0]!
  const filters: DmQueryFilters = {
    ...view.filters,
    scope,
    study: params.get('study') ?? undefined,
    site: params.get('site') ?? undefined,
    form: params.get('form') ?? undefined,
    raisedFrom: params.get('from') ?? undefined,
    raisedTo: params.get('to') ?? undefined,
    search: params.get('q') ?? undefined,
  }
  const overview = useDmOverview(scope)
  const multi = Boolean(overview.data?.multi)
  const { data, isLoading, isError, error } = useDmQueries(filters)

  const label = (options: { id: string; label: string }[] | undefined, id?: string) =>
    options?.find((o) => o.id === id)?.label ?? id
  const studyCode = overview.data?.studies.find((st) => st.connection === filters.study)?.study_code ?? filters.study
  const dates =
    filters.raisedFrom || filters.raisedTo
      ? `${filters.raisedFrom ? formatDay(filters.raisedFrom) : 'any'} – ${filters.raisedTo ? formatDay(filters.raisedTo) : 'any'}`
      : null
  // The less common filters, shown as removable tags while they are on.
  const active = [
    filters.study && { key: 'study', text: `Study: ${studyCode}`, clear: { study: undefined, site: undefined } },
    filters.site && { key: 'site', text: `Site: ${label(overview.data?.site_options, filters.site)}`, clear: { site: undefined } },
    filters.form && { key: 'form', text: `Form: ${label(overview.data?.form_options, filters.form)}`, clear: { form: undefined } },
    dates && { key: 'dates', text: `Raised: ${dates} (UTC)`, clear: { from: undefined, to: undefined } },
    filters.search && { key: 'q', text: `Search: “${filters.search}”`, clear: { q: undefined } },
  ].filter(Boolean) as { key: string; text: string; clear: Record<string, undefined> }[]
  const panelCount = active.filter((a) => a.key !== 'q').length

  const panel = (
    <Flex vertical gap={12} style={{ width: 300 }}>
      {multi && (
        <Flex vertical gap={4}>
          <Typography.Text strong>Study</Typography.Text>
          <Select
            aria-label="Study filter"
            allowClear
            placeholder="All studies in view"
            value={filters.study}
            onChange={(v?: string) => onChange({ study: v, site: undefined })}
            options={(overview.data?.studies ?? []).map((st) => ({ value: st.connection, label: st.study_code }))}
          />
        </Flex>
      )}
      <Flex vertical gap={4}>
        <Typography.Text strong>Site</Typography.Text>
        <Select
          aria-label="Site"
          allowClear
          showSearch
          optionFilterProp="label"
          placeholder="All sites"
          value={filters.site}
          onChange={(v?: string) => onChange({ site: v })}
          options={(overview.data?.site_options ?? []).map((o) => ({ value: o.id, label: o.label }))}
        />
      </Flex>
      <Flex vertical gap={4}>
        <Typography.Text strong>Form</Typography.Text>
        <Select
          aria-label="Form"
          allowClear
          showSearch
          optionFilterProp="label"
          placeholder="All forms"
          value={filters.form}
          onChange={(v?: string) => onChange({ form: v })}
          options={(overview.data?.form_options ?? []).map((o) => ({ value: o.id, label: o.label }))}
        />
      </Flex>
      <Flex vertical gap={4}>
        <Typography.Text strong>Raised between</Typography.Text>
        <DatePicker.RangePicker
          aria-label="Raised between"
          format="DD MMM YYYY"
          placeholder={['From', 'To']}
          allowEmpty={[true, true]}
          value={[filters.raisedFrom ? dayjs(filters.raisedFrom) : null, filters.raisedTo ? dayjs(filters.raisedTo) : null]}
          onChange={(range) =>
            onChange({
              from: range?.[0] ? range[0].format('YYYY-MM-DD') : undefined,
              to: range?.[1] ? range[1].format('YYYY-MM-DD') : undefined,
            })
          }
        />
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Days in UTC, as Viedoc records them.
        </Typography.Text>
      </Flex>
    </Flex>
  )

  return (
    <Flex vertical gap={12}>
      <div style={{ overflowX: 'auto' }}>
        <Segmented
          aria-label="Quick views"
          value={view.key}
          onChange={(v) => onChange({ view: v === 'attention' ? undefined : String(v) })}
          options={VIEWS.map((v) => ({
            value: v.key,
            label: (
              <span data-testid={`dm-view-${v.key}`}>
                {v.label}
                {data && <Badge count={data.views[v.key] ?? 0} showZero overflowCount={9999} color={v.key === 'overdue' ? '#B42318' : '#5B6B82'} style={{ marginLeft: 6 }} />}
              </span>
            ),
          }))}
        />
      </div>
      <Flex gap={8} align="center" wrap>
        <Input.Search
          aria-label="Search queries"
          placeholder="Search subject, query no., field or edit check"
          allowClear
          defaultValue={filters.search}
          key={filters.search ?? ''}
          onSearch={(v) => onChange({ q: v || undefined })}
          style={{ flex: '1 1 260px', maxWidth: 460 }}
        />
        <Popover content={panel} title="Filters" trigger="click" placement="bottomLeft">
          <Button icon={<FilterOutlined />}>
            Filters{panelCount ? ` (${panelCount})` : ''}
          </Button>
        </Popover>
      </Flex>
      {active.length > 0 && (
        <Flex gap={6} wrap align="center" data-testid="dm-active-filters">
          {active.map((a) => (
            <Tag key={a.key} closable onClose={() => onChange(a.clear)} style={{ marginInlineEnd: 0 }}>
              {a.text}
            </Tag>
          ))}
          <Button
            type="link"
            size="small"
            onClick={() => onChange({ study: undefined, site: undefined, form: undefined, from: undefined, to: undefined, q: undefined })}
          >
            Clear all
          </Button>
        </Flex>
      )}
      {isError && <Alert type="error" showIcon title="Could not load queries" description={error.message} />}
      {isLoading || !data ? (
        <Skeleton active paragraph={{ rows: 8 }} />
      ) : (
        <>
          <Typography.Text type="secondary" data-testid="dm-query-count">
            {data.total} quer{data.total === 1 ? 'y' : 'ies'} · overdue first, then longest waiting
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
              ...(multi ? [{ title: 'Study', dataIndex: 'study_code', width: 110 }] : []),
              { title: 'No.', dataIndex: 'query_number', width: 60 },
              { title: 'Site', dataIndex: 'site_code', width: 70 },
              { title: 'Subject', dataIndex: 'subject_id', width: 100 },
              { title: 'Visit', dataIndex: 'event_name', render: (v: string | null) => v ?? '—' },
              {
                title: 'Form · field',
                key: 'item',
                render: (_, r) => (
                  <span>
                    {r.form_label}
                    {r.item_label && <Typography.Text type="secondary"> · {r.item_label}</Typography.Text>}
                  </span>
                ),
              },
              { title: 'State', key: 'state', render: (_, r) => <StateTag q={r} /> },
              { title: 'Raised', dataIndex: 'raised_at', width: 110, render: (v: string | null) => (v ? formatDay(v.slice(0, 10)) : '—') },
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
