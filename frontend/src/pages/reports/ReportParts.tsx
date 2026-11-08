import { FilePdfOutlined, FileExcelOutlined } from '@ant-design/icons'
import { Button, Card, Flex, Select, Typography } from 'antd'
import type { ReactNode } from 'react'

import type { ReportOption, ReportSource, ReportTile } from '../../api/types'
import { formatDateTime } from '../../lib/format'
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

interface ToolbarProps {
  studyOptions: ReportOption[]
  siteOptions: ReportOption[]
  studyId?: string
  siteId?: string
  onStudy: (id?: string) => void
  onSite: (id?: string) => void
  source?: ReportSource
  excelUrl: string
}

/** Filters, "as of" line and exports (Excel download; PDF via the browser's Save as PDF). */
export function ReportToolbar(p: ToolbarProps) {
  return (
    <Card size="small" styles={{ body: { padding: '12px 16px' } }} className="no-print">
      <Flex gap={12} wrap align="flex-end">
        <Flex vertical gap={4}>
          <label htmlFor="report-study" style={{ fontSize: 12, fontWeight: 600, color: '#5B6B82' }}>
            Study
          </label>
          <Select
            id="report-study"
            aria-label="Filter by study"
            allowClear
            placeholder="All studies"
            value={p.studyId}
            onChange={(v?: string) => p.onStudy(v)}
            options={p.studyOptions.map((o) => ({ value: o.id, label: o.label }))}
            style={{ width: 300, maxWidth: '100%' }}
            popupMatchSelectWidth={false}
          />
        </Flex>
        <Flex vertical gap={4}>
          <label htmlFor="report-site" style={{ fontSize: 12, fontWeight: 600, color: '#5B6B82' }}>
            Site
          </label>
          <Select
            id="report-site"
            aria-label="Filter by site"
            allowClear
            placeholder="All sites"
            value={p.siteId}
            onChange={(v?: string) => p.onSite(v)}
            options={p.siteOptions.map((o) => ({ value: o.id, label: o.label }))}
            style={{ width: 260, maxWidth: '100%' }}
            popupMatchSelectWidth={false}
          />
        </Flex>
        <Typography.Text type="secondary" style={{ fontSize: 12, marginLeft: 'auto' }}>
          {p.source?.as_of ? `As of ${formatDateTime(p.source.as_of)}` : 'Not synced yet'} ·{' '}
          {p.source?.mode === 'api' ? 'Source: SimpleTrials (read-only copy)' : 'Source: demo data'}
        </Typography.Text>
        <Flex gap={8}>
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
