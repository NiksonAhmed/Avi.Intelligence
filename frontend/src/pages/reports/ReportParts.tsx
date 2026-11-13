import { FileExcelOutlined, FilePdfOutlined } from '@ant-design/icons'
import { Button, Card, Flex, Select, Typography } from 'antd'
import type { ReactNode } from 'react'

import type { ReportOption, ReportSource, ReportTile } from '../../api/types'
import { formatDateTime } from '../../lib/format'
import { SyncNowButton, type ReportSync } from '../../components/SyncNowButton'
import { INK } from '../../lib/reports'

/** Big-number tiles across the top of a report. */
export function ReportTiles({ tiles }: { tiles: ReportTile[] }) {
  return (
    <Flex gap={14} wrap>
      {tiles.map((t) => (
        <Card key={t.key} size="small" style={{ flex: '1 1 210px', minWidth: 0 }} styles={{ body: { padding: '14px 18px' } }}>
          <Flex vertical gap={4}>
            <Typography.Text type="secondary" style={{ fontSize: 13, fontWeight: 600 }}>
              {t.label}
            </Typography.Text>
            <span data-testid={`tile-${t.key}`} style={{ fontSize: 28, fontWeight: 700, lineHeight: 1.15, color: INK[t.tone] }}>
              {t.value}
            </span>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {t.note}
            </Typography.Text>
          </Flex>
        </Card>
      ))}
    </Flex>
  )
}

/** A chart card: title, the rule behind its numbers, then the chart. */
export function ChartCard({
  title,
  rule,
  extra,
  children,
  flex,
}: {
  title: string
  rule?: string
  extra?: ReactNode
  children: ReactNode
  flex?: string
}) {
  return (
    <Card
      size="small"
      style={{ flex: flex ?? '1 1 100%', minWidth: 0 }}
      styles={{ body: { padding: 20 } }}
      className="report-card"
    >
      <Flex vertical gap={12}>
        <Flex justify="space-between" align="baseline" gap={8} wrap>
          <Typography.Title level={2} style={{ margin: 0, fontSize: 17 }}>
            {title}
          </Typography.Title>
          {extra}
        </Flex>
        {rule && (
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {rule}
          </Typography.Text>
        )}
        {children}
      </Flex>
    </Card>
  )
}

/** A thin horizontal progress bar (percent 0–100+), with its colour. */
export function Bar({ percent, color, height = 10, label }: { percent: number; color: string; height?: number; label: string }) {
  return (
    <div
      role="img"
      aria-label={label}
      title={label}
      style={{ height, background: '#EEF1F5', borderRadius: height / 2, overflow: 'hidden' }}
    >
      <div style={{ width: `${Math.min(100, Math.max(0, percent))}%`, height: '100%', background: color, borderRadius: height / 2 }} />
    </div>
  )
}

/** One stacked horizontal bar: segments drawn in order, scaled to `max`. */
export function StackedBar({
  segments,
  max,
  label,
  height = 14,
}: {
  segments: { value: number; color: string }[]
  max: number
  label: string
  height?: number
}) {
  return (
    <div
      role="img"
      aria-label={label}
      title={label}
      style={{ display: 'flex', height, background: '#EEF1F5', borderRadius: 3, overflow: 'hidden' }}
    >
      {max > 0 &&
        segments
          .filter((seg) => seg.value > 0)
          .map((seg, i) => (
            <div key={i} style={{ width: `${(seg.value / max) * 100}%`, background: seg.color, height: '100%' }} />
          ))}
    </div>
  )
}

/** Small colour key for a chart. */
export function Legend({ items }: { items: { label: string; color: string }[] }) {
  return (
    <Flex gap={14} wrap style={{ fontSize: 12, color: '#3E4C5E' }} aria-hidden>
      {items.map((i) => (
        <Flex key={i.label} align="center" gap={6}>
          <span style={{ width: 12, height: 12, borderRadius: 2, background: i.color }} />
          {i.label}
        </Flex>
      ))}
    </Flex>
  )
}

export interface ToolbarFilter {
  id: string
  label: string
  ariaLabel: string
  placeholder: string
  value?: string
  options: ReportOption[]
  onChange: (value?: string) => void
  width?: number
}

interface ToolbarProps {
  filters: ToolbarFilter[]
  source?: ReportSource
  /** Overrides the "As of … · Source …" line. */
  sourceText?: string
  excelUrl: string
  /** Where Sync now pulls from: SimpleTrials, the SharePoint SOP library, or live app data (re-read). */
  sync: ReportSync
}

/** Filters, "as of" line and exports (Excel download; PDF via the browser's Save as PDF). */
export function ReportToolbar(p: ToolbarProps) {
  return (
    <Card size="small" styles={{ body: { padding: '12px 16px' } }} className="no-print">
      <Flex gap={12} wrap align="flex-end">
        {p.filters.map((f) => (
          <Flex key={f.id} vertical gap={4}>
            <label htmlFor={f.id} style={{ fontSize: 12, fontWeight: 600, color: '#5B6B82' }}>
              {f.label}
            </label>
            <Select
              id={f.id}
              aria-label={f.ariaLabel}
              allowClear
              placeholder={f.placeholder}
              value={f.value}
              onChange={(v?: string) => f.onChange(v)}
              options={f.options.map((o) => ({ value: o.id, label: o.label }))}
              style={{ width: f.width ?? 280, maxWidth: '100%' }}
              popupMatchSelectWidth={false}
            />
          </Flex>
        ))}
        <Typography.Text type="secondary" style={{ fontSize: 12, marginLeft: 'auto' }}>
          {p.sourceText ??
            `${p.source?.as_of ? `As of ${formatDateTime(p.source.as_of)}` : 'Not synced yet'} · ${
              p.source?.mode === 'api' ? 'Source: SimpleTrials (read-only copy)' : 'Source: demo data'
            }`}
        </Typography.Text>
        <Flex gap={8}>
          <SyncNowButton kind={p.sync} />
          <Button icon={<FileExcelOutlined />} href={p.excelUrl}>
            Excel
          </Button>
          <Button icon={<FilePdfOutlined />} onClick={() => window.print()}>
            PDF
          </Button>
        </Flex>
      </Flex>
    </Card>
  )
}
