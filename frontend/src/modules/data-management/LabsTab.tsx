import { ArrowDownOutlined, ArrowUpOutlined, FileExcelOutlined, FilterOutlined } from '@ant-design/icons'
import { Alert, Badge, Button, Card, DatePicker, Flex, Input, Popover, Segmented, Select, Skeleton, Table, Tag, Typography } from 'antd'
import dayjs from 'dayjs'
import type { HTMLAttributes } from 'react'

import { formatDay } from '../../lib/format'
import type { DmLabFilters, DmLabRow, DmLabView } from './api'
import { dmExportUrl, labParams, useDmLabs } from './api'
import { Tiles } from './OverviewTab'

interface Props {
  scope: string
  /** Excel download: System Admin and Data Manager only. */
  canExport: boolean
  params: URLSearchParams
  onChange: (changes: Record<string, string | undefined>) => void
}

const VIEWS: { key: DmLabView; label: string }[] = [
  { key: 'flagged', label: 'To check' },
  { key: 'out_of_range', label: 'Out of range' },
  { key: 'clin_sig', label: 'Clinically significant' },
  { key: 'missing', label: 'Missing results' },
  { key: 'no_evaluation', label: 'Not evaluated' },
  { key: 'no_unit', label: 'No unit' },
  { key: 'no_range', label: 'No normal range' },
  { key: 'all', label: 'All' },
]
/** Lab filters use their own names in the address, so other tabs keep their filters. */
const P = { view: 'lview', study: 'lstudy', site: 'lsite', form: 'lform', visit: 'lvisit', analyte: 'lanalyte', from: 'lfrom', to: 'lto', q: 'lq' }

const STATUS_TAG: Record<DmLabRow['status'], { color: string; label: string }> = {
  reported: { color: 'default', label: 'Reported' },
  missing: { color: 'orange', label: 'Missing' },
  not_done: { color: 'default', label: 'Not done' },
}
const EVALUATION_COLOUR: Record<string, string> = { normal: 'green', abnormal_ncs: 'gold', abnormal_cs: 'red', missing: 'orange' }
const ISSUE_COLOUR = (issue: string) =>
  issue.startsWith('Clinically') || issue.startsWith('No AE') ? 'red' : issue.startsWith('Out of range') ? 'volcano' : 'orange'

export function LabsTab({ scope, canExport, params, onChange }: Props) {
  const view = (VIEWS.find((v) => v.key === params.get(P.view))?.key ?? 'flagged') as DmLabView
  const filters: DmLabFilters = {
    scope,
    view,
    study: params.get(P.study) ?? undefined,
    site: params.get(P.site) ?? undefined,
    form: params.get(P.form) ?? undefined,
    visit: params.get(P.visit) ?? undefined,
    analyte: params.get(P.analyte) ?? undefined,
    visitFrom: params.get(P.from) ?? undefined,
    visitTo: params.get(P.to) ?? undefined,
    search: params.get(P.q) ?? undefined,
  }
  const { data, isLoading, isError, error } = useDmLabs(filters)

  if (isError) return <Alert type="error" showIcon title="Could not load labs" description={error.message} />
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
    filters.analyte && { key: 'analyte', text: `Analyte: ${filters.analyte}`, clear: { [P.analyte]: undefined } },
    dates && { key: 'dates', text: `Visit date: ${dates}`, clear: { [P.from]: undefined, [P.to]: undefined } },
    filters.search && { key: 'q', text: `Subject: “${filters.search}”`, clear: { [P.q]: undefined } },
  ].filter(Boolean) as { key: string; text: string; clear: Record<string, undefined> }[]
  const panelCount = active.filter((a) => a.key !== 'q').length
  const clearAll = Object.fromEntries(Object.values(P).filter((k) => k !== P.view).map((k) => [k, undefined]))

  const panel = (
    <Flex vertical gap={12} style={{ width: 300 }}>
      {data.multi && (
        <Select aria-label="Labs study" allowClear placeholder="All studies in view" value={filters.study}
          onChange={(v?: string) => onChange({ [P.study]: v, [P.site]: undefined })}
          options={data.studies.map((s) => ({ value: s.connection, label: s.study_code }))} />
      )}
      <Select aria-label="Labs site" allowClear showSearch optionFilterProp="label" placeholder="All sites" value={filters.site}
        onChange={(v?: string) => onChange({ [P.site]: v })} options={data.site_options.map((o) => ({ value: o.id, label: o.label }))} />
      <Select aria-label="Labs visit" allowClear showSearch optionFilterProp="label" placeholder="All visits" value={filters.visit}
        onChange={(v?: string) => onChange({ [P.visit]: v })} options={data.visit_options.map((o) => ({ value: o.id, label: o.label }))} />
      <Select aria-label="Labs form" allowClear showSearch optionFilterProp="label" placeholder="All lab forms" value={filters.form}
        onChange={(v?: string) => onChange({ [P.form]: v })} options={data.form_options.map((o) => ({ value: o.id, label: o.label }))} />
      <Select aria-label="Labs analyte" allowClear showSearch optionFilterProp="label" placeholder="All analytes" value={filters.analyte}
        onChange={(v?: string) => onChange({ [P.analyte]: v })} options={data.analyte_options.map((o) => ({ value: o.id, label: o.label }))} />
      <Flex vertical gap={4}>
        <Typography.Text strong>Visit date between</Typography.Text>
        <DatePicker.RangePicker
          aria-label="Lab visit date between"
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
      <Tiles tiles={data.tiles} percentKeys={['reported']} testIdPrefix="dm-labs-tile" />

      <Flex gap={16} wrap>
        <Card size="small" title="By analyte (most often missing first)" style={{ flex: '2 1 560px', minWidth: 0 }} styles={{ body: { padding: 0 } }}>
          <Table
            size="small"
            rowKey={(r) => `${r.form_label}:${r.analyte}`}
            pagination={data.analytes.length > 12 ? { pageSize: 12, showSizeChanger: false, size: 'small' } : false}
            dataSource={data.analytes}
            scroll={{ x: 640 }}
            onRow={() => ({ 'data-testid': 'dm-labs-analyte-row' }) as HTMLAttributes<HTMLElement>}
            columns={[
              {
                title: 'Analyte',
                key: 'analyte',
                render: (_, r) => (
                  <span>
                    <Button type="link" size="small" style={{ padding: 0 }} onClick={() => onChange({ [P.analyte]: r.analyte, [P.view]: 'all' })}>
                      {r.analyte}
                    </Button>
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}> · {r.form_label}</Typography.Text>
                  </span>
                ),
              },
              { title: 'Reported', key: 'rep', align: 'right', render: (_, r) => `${r.reported} / ${r.expected}` },
              {
                title: 'Missing',
                key: 'missing',
                align: 'right',
                render: (_, r) => (r.missing ? <Typography.Text type="warning">{r.missing} ({r.missing_percent ?? 0}%)</Typography.Text> : 0),
              },
              { title: 'Not done', dataIndex: 'not_done', align: 'right' },
              { title: 'Out of range', dataIndex: 'out_of_range', align: 'right' },
              { title: 'CS', dataIndex: 'clin_sig', align: 'right', render: (v: number) => (v ? <Typography.Text type="danger" strong>{v}</Typography.Text> : 0) },
              { title: 'No range', dataIndex: 'no_range', align: 'right' },
              { title: 'No unit', dataIndex: 'no_unit', align: 'right' },
            ]}
          />
        </Card>
        <Card size="small" title="By site" style={{ flex: '1 1 320px', minWidth: 0 }} styles={{ body: { padding: 0 } }}>
          <Table
            size="small"
            rowKey={(r) => `${r.connection}:${r.site_code}`}
            pagination={false}
            dataSource={data.sites}
            onRow={() => ({ 'data-testid': 'dm-labs-site-row' }) as HTMLAttributes<HTMLElement>}
            columns={[
              ...(data.multi ? [{ title: 'Study', dataIndex: 'study_code', key: 'study' }] : []),
              {
                title: 'Site',
                key: 'site',
                render: (_, r) => (
                  <Button type="link" size="small" style={{ padding: 0 }} onClick={() => onChange({ [P.site]: data.multi ? `${r.connection}:${r.site_code}` : r.site_code })}>
                    {r.site_code} · {r.site_name}
                  </Button>
                ),
              },
              { title: 'To check', dataIndex: 'flagged', align: 'right' },
              { title: 'Out of range', dataIndex: 'out_of_range', align: 'right' },
              { title: 'CS', dataIndex: 'clin_sig', align: 'right' },
            ]}
          />
        </Card>
      </Flex>

      <div style={{ overflowX: 'auto' }}>
        <Segmented
          aria-label="Lab views"
          value={view}
          onChange={(v) => onChange({ [P.view]: v === 'flagged' ? undefined : String(v) })}
          options={VIEWS.map((v) => ({
            value: v.key,
            label: (
              <span data-testid={`dm-labs-view-${v.key}`}>
                {v.label}
                <Badge count={data.views[v.key] ?? 0} showZero overflowCount={99999} color={v.key === 'clin_sig' && data.views.clin_sig ? '#C0392B' : '#5B6B82'} style={{ marginLeft: 6 }} />
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
          <Button icon={<FileExcelOutlined />} data-testid="dm-labs-excel" href={dmExportUrl('labs', labParams(filters))}>
            Download Excel
          </Button>
        )}
      </Flex>
      {active.length > 0 && (
        <Flex gap={6} wrap align="center" data-testid="dm-labs-active-filters">
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
      <Typography.Text type="secondary" data-testid="dm-labs-count">
        {data.total} result{data.total === 1 ? '' : 's'} · clinically significant first, then out of range
      </Typography.Text>
      <Table<DmLabRow>
        size="small"
        rowKey="id"
        dataSource={data.results}
        pagination={data.results.length > 50 ? { pageSize: 50, showSizeChanger: false } : false}
        scroll={{ x: 1040 }}
        onRow={() => ({ 'data-testid': 'dm-labs-row' }) as HTMLAttributes<HTMLElement>}
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
          { title: 'Analyte', dataIndex: 'analyte' },
          {
            title: 'Result',
            key: 'result',
            width: 140,
            render: (_, r) => (
              <Flex gap={4} align="center">
                <Tag color={STATUS_TAG[r.status].color} style={{ marginInlineEnd: 0 }}>{STATUS_TAG[r.status].label}</Tag>
                {r.out_of_range === 'high' && <Tag color="volcano" icon={<ArrowUpOutlined />} style={{ marginInlineEnd: 0 }}>High</Tag>}
                {r.out_of_range === 'low' && <Tag color="geekblue" icon={<ArrowDownOutlined />} style={{ marginInlineEnd: 0 }}>Low</Tag>}
              </Flex>
            ),
          },
          {
            title: 'Evaluation',
            key: 'evaluation',
            render: (_, r) =>
              r.evaluation_label ? <Tag color={EVALUATION_COLOUR[r.evaluation ?? ''] ?? 'default'}>{r.evaluation_label}</Tag> : <Typography.Text type="secondary">—</Typography.Text>,
          },
          {
            title: 'To check',
            key: 'issues',
            render: (_, r) => (
              <Flex gap={4} wrap>
                {r.issues
                  .filter((i) => !i.startsWith('Out of range (') && i !== 'Clinically significant' && i !== 'Result missing')
                  .map((i) => (
                    <Tag key={i} color={ISSUE_COLOUR(i)} style={{ marginInlineEnd: 0 }}>{i}</Tag>
                  ))}
              </Flex>
            ),
          },
        ]}
      />
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        {data.rules.labs} {data.rules.range} {data.rules.evaluation}
      </Typography.Text>
    </Flex>
  )
}
