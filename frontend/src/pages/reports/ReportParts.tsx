import {
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  FileExcelOutlined,
  FilePdfOutlined,
  InfoCircleOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import { Button, Card, Flex, Select, Tag, Tooltip, Typography } from 'antd'
import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'

import type { ReportInsights, ReportOption, ReportSource, ReportTile, TileTrend } from '../../api/types'
import { formatDateTime, formatDay } from '../../lib/format'
import { SyncNowButton, type ReportSync } from '../../components/SyncNowButton'
import { INK } from '../../lib/reports'

const HEADLINE_ICON = {
  good: <CheckCircleOutlined />,
  info: <InfoCircleOutlined />,
  neutral: <InfoCircleOutlined />,
  warn: <ExclamationCircleOutlined />,
  bad: <WarningOutlined />,
}
const HEADLINE_BG = { good: '#E7F6EE', info: '#E8F1FF', neutral: '#EEF1F5', warn: '#FFF4DE', bad: '#FDE8E4' }
const TREND_INK = { good: '#1A7F4B', bad: '#B42318', neutral: '#5B6B82' }

/** The headline sentence at the top of a report: what matters most, by fixed rules (no AI). */
export function ReportHeadline({ insights }: { insights?: ReportInsights }) {
  if (!insights) return null
  const since = insights.history_since
  // Until a few weeks of figures are saved, say when the history started.
  const young = since && Object.values(insights.trends).some((t) => t.points.length < 4)
  return (
    <Card size="small" data-testid="report-headline" styles={{ body: { padding: '16px 20px' } }}>
      <Flex gap={16} align="flex-start">
        <span
          aria-hidden
          style={{
            flexShrink: 0,
            width: 40,
            height: 40,
            borderRadius: 20,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 20,
            background: HEADLINE_BG[insights.tone],
            color: INK[insights.tone],
          }}
        >
          {HEADLINE_ICON[insights.tone]}
        </span>
        <Flex vertical gap={4}>
          <Typography.Text strong style={{ fontSize: 18, lineHeight: 1.4 }}>
            {insights.headline}
          </Typography.Text>
          {insights.detail && <Typography.Text type="secondary">{insights.detail}</Typography.Text>}
          {young && (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              Trend lines build up from {formatDay(since)}: Avi.Intelligence saves these figures once a day.
            </Typography.Text>
          )}
        </Flex>
      </Flex>
    </Card>
  )
}

/** A small trend line: one point a week. */
export function Sparkline({ points, color }: { points: number[]; color: string }) {
  if (points.length < 2) return null
  const min = Math.min(...points)
  const span = Math.max(...points) - min || 1
  const step = 92 / (points.length - 1)
  const line = points.map((v, i) => `${(2 + i * step).toFixed(1)},${(27 - ((v - min) / span) * 24).toFixed(1)}`).join(' ')
  return (
    <svg width="96" height="30" viewBox="0 0 96 30" aria-hidden data-testid="sparkline">
      <polyline points={line} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function TileBody({ t, trend }: { t: ReportTile; trend?: TileTrend }) {
  return (
    <Flex vertical gap={4}>
      <Typography.Text type="secondary" style={{ fontSize: 13, fontWeight: 600 }}>
        {t.label}
      </Typography.Text>
      <Flex justify="space-between" align="flex-end" gap={8}>
        <span data-testid={`tile-${t.key}`} style={{ fontSize: 28, fontWeight: 700, lineHeight: 1.15, color: INK[t.tone] }}>
          {t.value}
        </span>
        {trend && <Sparkline points={trend.points} color={INK[t.tone === 'neutral' ? 'info' : t.tone]} />}
      </Flex>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        {t.note}
      </Typography.Text>
      {trend?.change_text && (
        <span data-testid={`trend-${t.key}`} style={{ fontSize: 12, fontWeight: 600, color: TREND_INK[trend.tone] }}>
          {trend.change_text}
        </span>
      )}
    </Flex>
  )
}

/**
 * Big-number tiles across the top of a report, with their trend when there is history. A tile with a
 * `targets` entry jumps to the chart or list behind its number.
 */
export function ReportTiles({
  tiles,
  trends,
  targets,
}: {
  tiles: ReportTile[]
  trends?: Record<string, TileTrend>
  targets?: Record<string, string>
}) {
  return (
    <Flex gap={14} wrap>
      {tiles.map((t) => {
        const target = targets?.[t.key]
        const card = (
          <Card size="small" hoverable={Boolean(target)} style={{ height: '100%' }} styles={{ body: { padding: '14px 18px' } }}>
            <TileBody t={t} trend={trends?.[t.key]} />
          </Card>
        )
        return (
          <div key={t.key} style={{ flex: '1 1 210px', minWidth: 0 }}>
            {target ? (
              <button
                type="button"
                className="tile-button"
                aria-label={`${t.label}: ${t.value}. Show the detail`}
                onClick={() => {
                  const el = document.getElementById(target)
                  el?.closest('details')?.setAttribute('open', '')
                  el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
                }}
              >
                {card}
              </button>
            ) : (
              card
            )}
          </div>
        )
      })}
    </Flex>
  )
}

/** A chart card: title, the rule behind its numbers, then the chart. */
export function ChartCard({
  id,
  title,
  rule,
  extra,
  children,
  flex,
}: {
  /** Lets a tile jump here. */
  id?: string
  title: string
  rule?: string
  extra?: ReactNode
  children: ReactNode
  flex?: string
}) {
  return (
    <Card
      id={id}
      size="small"
      style={{ flex: flex ?? '1 1 100%', minWidth: 0, scrollMarginTop: 80 }}
      styles={{ body: { padding: '16px 20px' } }}
      className="report-card"
    >
      <Flex vertical gap={12}>
        <Flex justify="space-between" align="center" gap={8} wrap>
          <Flex align="center" gap={6}>
            <Typography.Title level={2} style={{ margin: 0, fontSize: 16 }}>
              {title}
            </Typography.Title>
            {rule && <RuleInfo rule={rule} />}
          </Flex>
          {extra}
        </Flex>
        {rule && (
          <Typography.Text type="secondary" className="print-only" style={{ fontSize: 12 }}>
            {rule}
          </Typography.Text>
        )}
        {children}
      </Flex>
    </Card>
  )
}

/** How a number is worked out, behind a small ⓘ (shown in full in the PDF). */
export function RuleInfo({ rule }: { rule: string }) {
  return (
    <Tooltip title={rule} placement="topLeft" styles={{ root: { maxWidth: 420 } }}>
      <button type="button" className="rule-info no-print" aria-label="How this is worked out" title={rule}>
        <InfoCircleOutlined />
      </button>
    </Tooltip>
  )
}

/** Two charts side by side (stacked on narrow screens). */
export function ChartRow({ children }: { children: ReactNode }) {
  return (
    <Flex gap={18} wrap>
      {children}
    </Flex>
  )
}

/** Everything beyond the main charts and table, folded away until wanted. */
export function MoreDetail({ summary, children }: { summary: string; children: ReactNode }) {
  const ref = useRef<HTMLDetailsElement>(null)
  useEffect(() => {
    // The PDF (browser print) shows everything, folded or not.
    const open = () => ref.current?.setAttribute('open', '')
    window.addEventListener('beforeprint', open)
    return () => window.removeEventListener('beforeprint', open)
  }, [])
  return (
    <details ref={ref} className="report-more" data-testid="more-detail">
      <summary>{summary}</summary>
      <Flex vertical gap={18} style={{ marginTop: 14 }}>
        {children}
      </Flex>
    </details>
  )
}

/** A small tag saying the figures are demo or sandbox data (instead of a large banner). */
export function SourceBadge({ source }: { source?: ReportSource }) {
  if (!source) return null
  if (source.mode !== 'api')
    return (
      <Tooltip title="SimpleTrials is not connected: these are demo figures.">
        <Tag color="orange" style={{ marginInlineEnd: 0 }}>Demo data</Tag>
      </Tooltip>
    )
  if (source.sandbox_only)
    return (
      <Tooltip title="Figures come from the SimpleTrials sandbox study only. All studies appear once the Workspace (all studies) read-only key is enabled.">
        <Tag color="purple" style={{ marginInlineEnd: 0 }}>Sandbox study</Tag>
      </Tooltip>
    )
  return null
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
  /** Where the figures come from, behind an ⓘ beside the "as of" line. */
  about?: string
  /** A small tag beside the filters, e.g. "Sandbox study" (defaults to the SimpleTrials source tag). */
  badge?: ReactNode
  excelUrl: string
  /** Where Sync now pulls from: SimpleTrials, the SharePoint SOP library, or live app data (re-read). */
  sync: ReportSync
}

/** One line: filters, the source tag and "as of", then Sync now, Excel and PDF (browser Save as PDF). */
export function ReportToolbar(p: ToolbarProps) {
  return (
    <Flex gap={12} wrap align="center" className="no-print report-toolbar">
      {p.filters.map((f) => (
        <Flex key={f.id} align="center" gap={6}>
          <label htmlFor={f.id} style={{ fontSize: 13, color: '#5B6B82' }}>
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
            style={{ width: Math.min(f.width ?? 200, 200), maxWidth: '100%' }}
            popupMatchSelectWidth={false}
          />
        </Flex>
      ))}
      {p.badge ?? <SourceBadge source={p.source} />}
      <Flex align="center" gap={6} style={{ marginLeft: 'auto' }}>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {p.sourceText ??
            `${p.source?.as_of ? `As of ${formatDateTime(p.source.as_of)}` : 'Not synced yet'} · ${
              p.source?.mode === 'api' ? 'SimpleTrials' : 'demo data'
            }`}
        </Typography.Text>
        {p.about && <RuleInfo rule={p.about} />}
      </Flex>
      <Flex gap={8}>
        <SyncNowButton kind={p.sync} />
        <Button type="primary" icon={<FileExcelOutlined />} href={p.excelUrl}>
          Excel
        </Button>
        <Button icon={<FilePdfOutlined />} onClick={() => window.print()}>
          PDF
        </Button>
      </Flex>
    </Flex>
  )
}
