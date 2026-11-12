import { FileExcelOutlined, FilterOutlined } from '@ant-design/icons'
import { Alert, Badge, Button, Card, DatePicker, Flex, Input, Popover, Segmented, Select, Skeleton, Table, Tag, Typography } from 'antd'
import dayjs from 'dayjs'
import type { HTMLAttributes } from 'react'

import { formatDay } from '../../lib/format'
import type { DmFlag, DmMissing, DmMissingFilters, DmMissingRow, DmMissingView } from './api'
import { dmExportUrl, missingParams, useDmMissing } from './api'
import { Tiles } from './OverviewTab'

interface Props {
  scope: string
  /** Excel download: System Admin and Data Manager only. */
  canExport: boolean
  params: URLSearchParams
  onChange: (changes: Record<string, string | undefined>) => void
}

const VIEWS: { key: DmMissingView; label: string }[] = [
  { key: 'fields', label: 'Missing fields' },
  { key: 'overdue', label: 'Overdue' },
  { key: 'pending', label: 'Pending forms' },
  { key: 'upgrade', label: 'Awaiting upgrade' },
]
/** Missing data filters use their own names in the address, so other tabs keep their filters. */
const P = { view: 'mview', study: 'mstudy', site: 'msite', form: 'mform', visit: 'mvisit', from: 'mfrom', to: 'mto', q: 'mq' }

const TARGET_TAG: Record<DmFlag, { color: string; label: string } | null> = {
  red: { color: 'red', label: 'Overdue' },
  amber: { color: 'gold', label: 'Last day' },
  green: { color: 'green', label: 'Within target' },
  none: null,
}

function BySite({ data, onSite }: { data: DmMissing; onSite: (site: string) => void }) {
  return (
    <Table
      size="small"
      rowKey={(r) => `${r.connection}:${r.site_code}`}
      pagination={false}
      dataSource={data.sites}
      scroll={{ x: 560 }}
      onRow={() => ({ 'data-testid': 'dm-missing-site-row' }) as HTMLAttributes<HTMLElement>}
      columns={[
        ...(data.multi ? [{ title: 'Study', dataIndex: 'study_code', key: 'study' }] : []),
        {
          title: 'Site',
          key: 'site',
          render: (_, r) => (
            <Button type="link" size="small" style={{ padding: 0 }} onClick={() => onSite(data.multi ? `${r.connection}:${r.site_code}` : r.site_code)}>
              {r.site_code} · {r.site_name}
            </Button>
          ),
        },
        { title: 'Missing fields', dataIndex: 'fields', align: 'right' },
        {
          title: 'Overdue',
          dataIndex: 'overdue',
          align: 'right',
          render: (v: number) => (v ? <Typography.Text type="danger" strong>{v}</Typography.Text> : 0),
        },
        { title: 'Pending forms', dataIndex: 'pending_forms', align: 'right' },
        { title: 'Awaiting upgrade', dataIndex: 'upgrades', align: 'right' },
        { title: 'Oldest (days)', dataIndex: 'oldest_days', align: 'right', render: (v: number | null) => v ?? '—' },
      ]}
    />
  )
}

export function MissingTab({ scope, canExport, params, onChange }: Props) {
  const view = (VIEWS.find((v) => v.key === params.get(P.view))?.key ?? 'fields') as DmMissingView
  const filters: DmMissingFilters = {
    scope,
    view,
    study: params.get(P.study) ?? undefined,
    site: params.get(P.site) ?? undefined,
    form: params.get(P.form) ?? undefined,
    visit: params.get(P.visit) ?? undefined,
    sinceFrom: params.get(P.from) ?? undefined,
    sinceTo: params.get(P.to) ?? undefined,
    search: params.get(P.q) ?? undefined,
  }
  const { data, isLoading, isError, error } = useDmMissing(filters)

  if (isError) return <Alert type="error" showIcon title="Could not load missing data" description={error.message} />
  if (isLoading || !data) return <Skeleton active paragraph={{ rows: 8 }} />

  const name = (options: { id: string; label: string }[], id?: string) => options.find((o) => o.id === id)?.label ?? id
  const dates =
    filters.sinceFrom || filters.sinceTo
      ? `${filters.sinceFrom ? formatDay(filters.sinceFrom) : 'any'} – ${filters.sinceTo ? formatDay(filters.sinceTo) : 'any'}`
      : null
  const active = [
    filters.study && { key: 'study', text: `Study: ${data.studies.find((s) => s.connection === filters.study)?.study_code ?? filters.study}`, clear: { [P.study]: undefined, [P.site]: undefined } },
    filters.site && { key: 'site', text: `Site: ${name(data.site_options, filters.site)}`, clear: { [P.site]: undefined } },
    filters.visit && { key: 'visit', text: `Visit: ${name(data.visit_options, filters.visit)}`, clear: { [P.visit]: undefined } },
    filters.form && { key: 'form', text: `Form: ${name(data.form_options, filters.form)}`, clear: { [P.form]: undefined } },
    dates && { key: 'dates', text: `Since: ${dates}`, clear: { [P.from]: undefined, [P.to]: undefined } },
    filters.search && { key: 'q', text: `Subject: “${filters.search}”`, clear: { [P.q]: undefined } },
  ].filter(Boolean) as { key: string; text: string; clear: Record<string, undefined> }[]
  const panelCount = active.filter((a) => a.key !== 'q').length
  const clearAll = Object.fromEntries(Object.values(P).filter((k) => k !== P.view).map((k) => [k, undefined]))

  const panel = (
    <Flex vertical gap={12} style={{ width: 300 }}>
      {data.multi && (
        <Select aria-label="Missing data study" allowClear placeholder="All studies in view" value={filters.study}
          onChange={(v?: string) => onChange({ [P.study]: v, [P.site]: undefined })}
          options={data.studies.map((s) => ({ value: s.connection, label: s.study_code }))} />
      )}
      <Select aria-label="Missing data site" allowClear showSearch optionFilterProp="label" placeholder="All sites" value={filters.site}
        onChange={(v?: string) => onChange({ [P.site]: v })} options={data.site_options.map((o) => ({ value: o.id, label: o.label }))} />
      <Select aria-label="Missing data visit" allowClear showSearch optionFilterProp="label" placeholder="All visits" value={filters.visit}
        onChange={(v?: string) => onChange({ [P.visit]: v })} options={data.visit_options.map((o) => ({ value: o.id, label: o.label }))} />
      <Select aria-label="Missing data form" allowClear showSearch optionFilterProp="label" placeholder="All forms" value={filters.form}
        onChange={(v?: string) => onChange({ [P.form]: v })} options={data.form_options.map((o) => ({ value: o.id, label: o.label }))} />
      <Flex vertical gap={4}>
        <Typography.Text strong>Missing or pending since</Typography.Text>
        <DatePicker.RangePicker
          aria-label="Missing since"
          format="DD MMM YYYY"
          placeholder={['From', 'To']}
          allowEmpty={[true, true]}
          value={[filters.sinceFrom ? dayjs(filters.sinceFrom) : null, filters.sinceTo ? dayjs(filters.sinceTo) : null]}
          onChange={(range) =>
            onChange({
              [P.from]: range?.[0] ? range[0].format('YYYY-MM-DD') : undefined,
              [P.to]: range?.[1] ? range[1].format('YYYY-MM-DD') : undefined,
            })
          }
        />
      </Flex>
    </Flex>
  )

  return (
    <Flex vertical gap={16}>
      <Tiles tiles={data.tiles} testIdPrefix="dm-missing-tile" />

      <Flex gap={16} wrap>
        <Card size="small" title="By site (most overdue first)" style={{ flex: '2 1 520px', minWidth: 0 }} styles={{ body: { padding: 0 } }}>
          <BySite data={data} onSite={(site) => onChange({ [P.site]: site })} />
        </Card>
        <Card size="small" title="Subjects with the most gaps" style={{ flex: '1 1 300px', minWidth: 0 }} styles={{ body: { padding: 0 } }}>
          <Table
            size="small"
            rowKey={(r) => `${r.connection}:${r.subject_id}`}
            pagination={false}
            dataSource={data.subjects}
            onRow={() => ({ 'data-testid': 'dm-missing-subject-row' }) as HTMLAttributes<HTMLElement>}
            columns={[
              {
                title: 'Subject',
                key: 'subject',
                render: (_, r) => (
                  <Button type="link" size="small" style={{ padding: 0 }} onClick={() => onChange({ [P.q]: r.subject_id })}>
                    {r.subject_id}
                  </Button>
                ),
              },
              { title: 'Fields', dataIndex: 'fields', align: 'right' },
              { title: 'Forms', dataIndex: 'pending_forms', align: 'right' },
              { title: 'Oldest', dataIndex: 'oldest_days', align: 'right', render: (v: number | null) => (v === null ? '—' : `${v} d`) },
            ]}
          />
        </Card>
      </Flex>

      <Flex gap={16} wrap>
        <Card size="small" title="Fields most often left blank" style={{ flex: '1 1 380px', minWidth: 0 }}>
          <Flex vertical gap={6}>
            {data.top_fields.length === 0 && <Typography.Text type="secondary">No missing fields.</Typography.Text>}
            {data.top_fields.map((f) => (
              <Flex key={`${f.form_label}:${f.item_label}`} justify="space-between" gap={12} data-testid="dm-missing-top-field">
                <span>
                  {f.item_label} <Typography.Text type="secondary">· {f.form_label}</Typography.Text>
                </span>
                <span style={{ whiteSpace: 'nowrap' }}>
                  {f.subjects} subject{f.subjects === 1 ? '' : 's'}
                </span>
              </Flex>
            ))}
          </Flex>
        </Card>
        <Card size="small" title="By visit" style={{ flex: '1 1 300px', minWidth: 0 }}>
          <Flex vertical gap={6}>
            {data.visits.map((v) => (
              <Flex key={v.id} justify="space-between" gap={12} data-testid="dm-missing-visit-row">
                <Button type="link" size="small" style={{ padding: 0 }} onClick={() => onChange({ [P.visit]: v.id })}>
                  {v.label}
                </Button>
                <span style={{ fontSize: 12 }}>
                  {v.fields} fields · {v.pending_forms} forms
                </span>
              </Flex>
            ))}
          </Flex>
        </Card>
      </Flex>

      <div style={{ overflowX: 'auto' }}>
        <Segmented
          aria-label="Missing data views"
          value={view}
          onChange={(v) => onChange({ [P.view]: v === 'fields' ? undefined : String(v) })}
          options={VIEWS.map((v) => ({
            value: v.key,
            label: (
              <span data-testid={`dm-missing-view-${v.key}`}>
                {v.label}
                <Badge count={data.views[v.key] ?? 0} showZero overflowCount={99999} color={v.key === 'overdue' && data.views.overdue ? '#C0392B' : '#5B6B82'} style={{ marginLeft: 6 }} />
              </span>
            ),
          }))}
        />
      </div>
      <Flex gap={8} align="center" wrap>
        <Input.Search aria-label="Search subject" placeholder="Search subject ID" allowClear defaultValue={filters.search}
          key={filters.search ?? ''} onSearch={(v) => onChange({ [P.q]: v || undefined })} style={{ flex: '1 1 240px', maxWidth: 380 }} />
        <Popover content={panel} title="Filters" trigger="click" placement="bottomLeft">
          <Button icon={<FilterOutlined />}>Filters{panelCount ? ` (${panelCount})` : ''}</Button>
        </Popover>
        {canExport && (
          <Button icon={<FileExcelOutlined />} data-testid="dm-missing-excel" href={dmExportUrl('missing', missingParams(filters))}>
            Download Excel
          </Button>
        )}
      </Flex>
      {active.length > 0 && (
        <Flex gap={6} wrap align="center" data-testid="dm-missing-active-filters">
          {active.map((a) => (
            <Tag key={a.key} closable onClose={() => onChange(a.clear)} style={{ marginInlineEnd: 0 }}>
              {a.text}
            </Tag>
          ))}
          <Button type="link" size="small" onClick={() => onChange(clearAll)}>
            Clear all
          </Button>
        </Flex>
      )}
      <Typography.Text type="secondary" data-testid="dm-missing-count">
        {data.total} {view === 'pending' || view === 'upgrade' ? `form${data.total === 1 ? '' : 's'}` : `item${data.total === 1 ? '' : 's'}`} · overdue first, then longest waiting
      </Typography.Text>
      <Table<DmMissingRow>
        size="small"
        rowKey="id"
        dataSource={data.items}
        pagination={data.items.length > 50 ? { pageSize: 50, showSizeChanger: false } : false}
        scroll={{ x: 960 }}
        onRow={() => ({ 'data-testid': 'dm-missing-row' }) as HTMLAttributes<HTMLElement>}
        columns={[
          ...(data.multi ? [{ title: 'Study', dataIndex: 'study_code', width: 110 }] : []),
          { title: 'Site', dataIndex: 'site_code', width: 70 },
          { title: 'Subject', dataIndex: 'subject_id', width: 100 },
          {
            title: 'Visit',
            key: 'visit',
            render: (_, r) => (
              <span>
                {r.event_name ?? '—'}
                {r.event_date && <Typography.Text type="secondary"> · {formatDay(r.event_date.slice(0, 10))}</Typography.Text>}
              </span>
            ),
          },
          { title: 'Form', dataIndex: 'form_label' },
          ...(view === 'fields' || view === 'overdue'
            ? [{ title: 'Field', key: 'field', render: (_: unknown, r: DmMissingRow) => r.item_label ?? (r.kind === 'pending' ? <Typography.Text type="secondary">Whole form pending</Typography.Text> : '—') }]
            : []),
          { title: 'Since', key: 'since', width: 120, render: (_, r) => (r.since ? formatDay(r.since.slice(0, 10)) : '—') },
          { title: 'Days', dataIndex: 'days', align: 'right', width: 70, render: (v: number | null) => v ?? '—' },
          {
            title: `Target (${data.target_days} wd)`,
            key: 'target',
            width: 130,
            render: (_, r) => {
              if (r.kind === 'upgrade') return <Typography.Text type="secondary">—</Typography.Text>
              const tag = TARGET_TAG[r.flag]
              return tag ? <Tag color={tag.color} title={`${r.working_days ?? 0} working days`}>{tag.label}</Tag> : '—'
            },
          },
        ]}
      />
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        {data.rules.missing} {data.rules.target} Read-only: sites enter or confirm data in Viedoc; changes appear after the next sync.
      </Typography.Text>
    </Flex>
  )
}
