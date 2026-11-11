import { CheckCircleFilled, FileExcelOutlined, FilterOutlined } from '@ant-design/icons'
import { Alert, Badge, Button, Card, DatePicker, Flex, Input, Popover, Progress, Segmented, Select, Skeleton, Table, Tag, Typography } from 'antd'
import dayjs from 'dayjs'
import type { HTMLAttributes } from 'react'

import { formatDay } from '../../lib/format'
import type { DmSdv, DmSdvFilters, DmSdvForm } from './api'
import { dmExportUrl, useDmSdv } from './api'
import { Tiles } from './OverviewTab'

interface Props {
  scope: string
  /** Excel download: System Admin and Data Manager only. */
  canExport: boolean
  params: URLSearchParams
  onChange: (changes: Record<string, string | undefined>) => void
}

type View = 'waiting' | 'complete' | 'all'
const VIEWS: { key: View; label: string }[] = [
  { key: 'waiting', label: 'Waiting for SDV' },
  { key: 'complete', label: 'Fully verified' },
  { key: 'all', label: 'All' },
]
/** SDV filters use their own names in the address, so the Queries tab keeps its own filters. */
const P = { view: 'sview', study: 'sstudy', site: 'ssite', form: 'sform', visit: 'svisit', from: 'sfrom', to: 'sto', q: 'sq' }

function pctColour(p: number | null): string {
  if (p === null) return '#8A97A8'
  if (p >= 100) return '#1E7F4F'
  if (p >= 50) return '#1F4E8C'
  return '#B26B00'
}

function Done({ at, label }: { at: string | null; label: string }) {
  if (!at) return <Typography.Text type="secondary">—</Typography.Text>
  return (
    <span title={`${label} ${formatDay(at.slice(0, 10))}`} style={{ whiteSpace: 'nowrap' }}>
      <CheckCircleFilled style={{ color: '#1E7F4F', marginRight: 4 }} aria-hidden />
      {formatDay(at.slice(0, 10))}
    </span>
  )
}

function SiteProgress({ data, onSite }: { data: DmSdv; onSite: (site: string) => void }) {
  return (
    <Table
      size="small"
      rowKey={(r) => `${r.connection}:${r.site_code}`}
      pagination={false}
      dataSource={data.sites}
      scroll={{ x: 560 }}
      onRow={() => ({ 'data-testid': 'dm-sdv-site-row' }) as HTMLAttributes<HTMLElement>}
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
        {
          title: 'Fields verified',
          key: 'pct',
          width: 220,
          render: (_, r) => (
            <Flex align="center" gap={8} title={`${r.done} of ${r.required} fields`}>
              <Progress percent={r.percent ?? 0} size="small" showInfo={false} strokeColor={pctColour(r.percent)} style={{ flex: 1, margin: 0 }} />
              <span style={{ width: 110, textAlign: 'right', fontSize: 12 }}>
                {r.done} / {r.required} ({r.percent ?? 0}%)
              </span>
            </Flex>
          ),
        },
        { title: 'Forms waiting', dataIndex: 'forms_waiting', align: 'right' },
        { title: 'Oldest waiting (days)', dataIndex: 'oldest_waiting_days', align: 'right', render: (v: number | null) => v ?? '—' },
      ]}
    />
  )
}

export function SdvTab({ scope, canExport, params, onChange }: Props) {
  const view = (VIEWS.find((v) => v.key === params.get(P.view))?.key ?? 'waiting') as View
  const filters: DmSdvFilters = {
    scope,
    view,
    study: params.get(P.study) ?? undefined,
    site: params.get(P.site) ?? undefined,
    form: params.get(P.form) ?? undefined,
    visit: params.get(P.visit) ?? undefined,
    visitFrom: params.get(P.from) ?? undefined,
    visitTo: params.get(P.to) ?? undefined,
    search: params.get(P.q) ?? undefined,
  }
  const { data, isLoading, isError, error } = useDmSdv(filters)

  if (isError) return <Alert type="error" showIcon title="Could not load SDV" description={error.message} />
  if (isLoading || !data) return <Skeleton active paragraph={{ rows: 8 }} />

  const name = (options: { id: string; label: string }[], id?: string) => options.find((o) => o.id === id)?.label ?? id
  const dates =
    filters.visitFrom || filters.visitTo
      ? `${filters.visitFrom ? formatDay(filters.visitFrom) : 'any'} – ${filters.visitTo ? formatDay(filters.visitTo) : 'any'}`
      : null
  const active = [
    filters.study && { key: 'study', text: `Study: ${data.studies.find((s) => s.connection === filters.study)?.study_code ?? filters.study}`, clear: { [P.study]: undefined, [P.site]: undefined } },
    filters.site && { key: 'site', text: `Site: ${name(data.site_options, filters.site)}`, clear: { [P.site]: undefined } },
    filters.visit && { key: 'visit', text: `Visit: ${name(data.visit_options, filters.visit)}`, clear: { [P.visit]: undefined } },
    filters.form && { key: 'form', text: `Form: ${name(data.form_options, filters.form)}`, clear: { [P.form]: undefined } },
    dates && { key: 'dates', text: `Visit date: ${dates}`, clear: { [P.from]: undefined, [P.to]: undefined } },
    filters.search && { key: 'q', text: `Subject: “${filters.search}”`, clear: { [P.q]: undefined } },
  ].filter(Boolean) as { key: string; text: string; clear: Record<string, undefined> }[]
  const panelCount = active.filter((a) => a.key !== 'q').length
  const clearAll = Object.fromEntries(Object.values(P).filter((k) => k !== P.view).map((k) => [k, undefined]))

  const panel = (
    <Flex vertical gap={12} style={{ width: 300 }}>
      {data.multi && (
        <Select aria-label="SDV study" allowClear placeholder="All studies in view" value={filters.study}
          onChange={(v?: string) => onChange({ [P.study]: v, [P.site]: undefined })}
          options={data.studies.map((s) => ({ value: s.connection, label: s.study_code }))} />
      )}
      <Select aria-label="SDV site" allowClear showSearch optionFilterProp="label" placeholder="All sites" value={filters.site}
        onChange={(v?: string) => onChange({ [P.site]: v })} options={data.site_options.map((o) => ({ value: o.id, label: o.label }))} />
      <Select aria-label="SDV visit" allowClear showSearch optionFilterProp="label" placeholder="All visits" value={filters.visit}
        onChange={(v?: string) => onChange({ [P.visit]: v })} options={data.visit_options.map((o) => ({ value: o.id, label: o.label }))} />
      <Select aria-label="SDV form" allowClear showSearch optionFilterProp="label" placeholder="All forms" value={filters.form}
        onChange={(v?: string) => onChange({ [P.form]: v })} options={data.form_options.map((o) => ({ value: o.id, label: o.label }))} />
      <Flex vertical gap={4}>
        <Typography.Text strong>Visit date between</Typography.Text>
        <DatePicker.RangePicker
          aria-label="Visit date between"
          format="DD MMM YYYY"
          placeholder={['From', 'To']}
          allowEmpty={[true, true]}
          value={[filters.visitFrom ? dayjs(filters.visitFrom) : null, filters.visitTo ? dayjs(filters.visitTo) : null]}
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
      <Tiles tiles={data.tiles} percentKeys={['fields', 'data_review', 'signed', 'locked']} testIdPrefix="dm-sdv-tile" />

      <Flex gap={16} wrap>
        <Card size="small" title="SDV by site (lowest first)" style={{ flex: '2 1 520px', minWidth: 0 }} styles={{ body: { padding: 0 } }}>
          <SiteProgress data={data} onSite={(site) => onChange({ [P.site]: site })} />
        </Card>
        <Card size="small" title="SDV by visit" style={{ flex: '1 1 300px', minWidth: 0 }}>
          <Flex vertical gap={10}>
            {data.visits.map((v) => (
              <Flex key={v.event_id} vertical gap={2} data-testid="dm-sdv-visit-row">
                <Flex justify="space-between">
                  <Button type="link" size="small" style={{ padding: 0 }} onClick={() => onChange({ [P.visit]: v.event_id })}>
                    {v.event_name}
                  </Button>
                  <span style={{ fontSize: 12 }}>
                    {v.done} / {v.required} ({v.percent ?? 0}%)
                  </span>
                </Flex>
                <Progress percent={v.percent ?? 0} size="small" showInfo={false} strokeColor={pctColour(v.percent)} />
              </Flex>
            ))}
          </Flex>
        </Card>
      </Flex>

      <div style={{ overflowX: 'auto' }}>
        <Segmented
          aria-label="SDV views"
          value={view}
          onChange={(v) => onChange({ [P.view]: v === 'waiting' ? undefined : String(v) })}
          options={VIEWS.map((v) => ({
            value: v.key,
            label: (
              <span data-testid={`dm-sdv-view-${v.key}`}>
                {v.label}
                <Badge count={data.views[v.key] ?? 0} showZero overflowCount={99999} color="#5B6B82" style={{ marginLeft: 6 }} />
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
          <Button
            icon={<FileExcelOutlined />}
            data-testid="dm-sdv-excel"
            href={dmExportUrl('sdv', {
              scope: filters.scope,
              study: filters.study,
              view: filters.view,
              site: filters.site,
              form: filters.form,
              visit: filters.visit,
              visit_from: filters.visitFrom,
              visit_to: filters.visitTo,
              search: filters.search,
            })}
          >
            Download Excel
          </Button>
        )}
      </Flex>
      {active.length > 0 && (
        <Flex gap={6} wrap align="center" data-testid="dm-sdv-active-filters">
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
      <Typography.Text type="secondary" data-testid="dm-sdv-count">
        {data.total} form{data.total === 1 ? '' : 's'} · oldest visit first
      </Typography.Text>
      <Table<DmSdvForm>
        size="small"
        rowKey="id"
        dataSource={data.forms}
        pagination={data.forms.length > 50 ? { pageSize: 50, showSizeChanger: false } : false}
        scroll={{ x: 1000 }}
        onRow={() => ({ 'data-testid': 'dm-sdv-form-row' }) as HTMLAttributes<HTMLElement>}
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
          {
            title: 'SDV',
            key: 'sdv',
            width: 170,
            render: (_, r) => (
              <Flex align="center" gap={6} title={r.last_sdv_at ? `Last verified ${formatDay(r.last_sdv_at.slice(0, 10))}` : undefined}>
                <Progress percent={r.percent ?? 0} size="small" showInfo={false} strokeColor={pctColour(r.percent)} style={{ width: 70, margin: 0 }} />
                <span style={{ fontSize: 12 }}>
                  {r.done} / {r.required}
                </span>
              </Flex>
            ),
          },
          { title: 'Data review', key: 'review', render: (_, r) => <Done at={r.data_review_at} label="Data reviewed" /> },
          { title: 'Signed', key: 'signed', render: (_, r) => <Done at={r.signed_at} label="Signed" /> },
          { title: 'Locked', key: 'locked', render: (_, r) => <Done at={r.locked_at} label="Locked" /> },
          { title: 'Days since visit', dataIndex: 'days_since_visit', align: 'right', width: 110, render: (v: number | null) => v ?? '—' },
        ]}
      />
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        {data.rules.sdv} {data.rules.review} Read-only: SDV is done in Viedoc; changes appear after the next sync.
      </Typography.Text>
    </Flex>
  )
}
