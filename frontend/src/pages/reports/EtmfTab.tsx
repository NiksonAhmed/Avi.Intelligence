import { Alert, Button, Empty, Flex, Skeleton, Typography } from 'antd'

import { reportExportUrl } from '../../api/client'
import { useEtmfReport } from '../../api/hooks'
import type { EtmfCompleteness, EtmfReport, ReportFilters, ReportTone } from '../../api/types'
import { ToneTag } from '../../components/ToneTag'
import { formatDay } from '../../lib/format'
import { INK, completenessTone, todayIso, toneStyle } from '../../lib/reports'
import { TONES } from '../../lib/studies'
import { Bar, ChartCard, ReportTiles, ReportToolbar } from './ReportParts'

interface Props {
  filters: ReportFilters
  onFilters: (next: ReportFilters) => void
}

function figure(c: EtmfCompleteness): string {
  return c.expected ? `${c.filed} of ${c.expected} (${c.percent}%)` : 'No documents expected'
}

/** A ring showing the share filed, with the percentage in the middle. */
function Donut({ c }: { c: EtmfCompleteness }) {
  const pct = c.percent ?? 0
  const r = 52
  const len = 2 * Math.PI * r
  const tone = completenessTone(c.percent)
  return (
    <svg width={140} height={140} viewBox="0 0 140 140" role="img" aria-label={`eTMF completeness: ${figure(c)}`}>
      <circle cx={70} cy={70} r={r} fill="none" stroke="#EEF1F5" strokeWidth={16} />
      <circle
        cx={70}
        cy={70}
        r={r}
        fill="none"
        stroke={INK[tone]}
        strokeWidth={16}
        strokeDasharray={`${(pct / 100) * len} ${len}`}
        transform="rotate(-90 70 70)"
      />
      <text x={70} y={68} textAnchor="middle" fontSize={24} fontWeight={700} fill={INK.neutral}>
        {c.percent !== null ? `${c.percent}%` : '—'}
      </text>
      <text x={70} y={88} textAnchor="middle" fontSize={11} fill="#5B6B82">
        filed
      </text>
    </svg>
  )
}

function CompletenessRows({ rows, testId, empty }: { rows: EtmfCompleteness[]; testId: string; empty: string }) {
  if (rows.length === 0) return <Typography.Text type="secondary">{empty}</Typography.Text>
  return (
    <Flex vertical gap={12} style={{ flex: '1 1 260px', minWidth: 0 }}>
      {rows.map((c) => {
        const tone = completenessTone(c.percent)
        return (
          <Flex key={c.key} vertical gap={6} data-testid={testId}>
            <Flex justify="space-between" gap={8}>
              <span style={{ fontWeight: 600 }}>{c.label}</span>
              <span style={{ fontSize: 13, fontWeight: 700, color: INK[tone], whiteSpace: 'nowrap' }}>
                {testId === 'site-missing-row' ? `${c.missing} missing · ` : ''}
                {figure(c)}
              </span>
            </Flex>
            <Bar percent={c.percent ?? 0} color={INK[tone]} label={`${c.label}: ${figure(c)}, ${c.missing} missing`} />
          </Flex>
        )
      })}
    </Flex>
  )
}

/** Sites (rows) by TMF section (columns): the share of expected documents filed. */
export function SectionHeatMap({ report }: { report: EtmfReport }) {
  if (report.heat_map.length === 0) return <Empty description="No site documents in this selection." />
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ borderCollapse: 'separate', borderSpacing: 3, minWidth: 140 + report.sections.length * 96 }}>
        <caption className="sr-only">Share of expected documents filed, by site and TMF section</caption>
        <thead>
          <tr>
            <th scope="col" style={{ textAlign: 'left', fontSize: 12, color: '#5B6B82' }}>
              Site
            </th>
            {report.sections.map((s) => (
              <th key={s} scope="col" style={{ fontSize: 11, color: '#5B6B82', fontWeight: 600, width: 96, verticalAlign: 'bottom' }}>
                {s}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {report.heat_map.map((row) => (
            <tr key={row.site_id} data-testid="heat-row">
              <th scope="row" style={{ textAlign: 'left', fontSize: 13, fontWeight: 600, paddingRight: 8, whiteSpace: 'nowrap' }}>
                {row.label}
                <div style={{ fontSize: 11, color: '#5B6B82', fontWeight: 400 }}>{row.protocol_number}</div>
              </th>
              {row.cells.map((c) => {
                if (!c.expected) {
                  return (
                    <td key={c.key} style={{ textAlign: 'center', color: '#8A97A8', fontSize: 12 }} title={`${row.label}, ${c.label}: none expected`}>
                      —
                    </td>
                  )
                }
                const t = TONES[completenessTone(c.percent)]
                return (
                  <td
                    key={c.key}
                    title={`${row.label}, ${c.label}: ${figure(c)}`}
                    style={{ background: t.background, border: `1px solid ${t.border}`, color: t.color, borderRadius: 4, textAlign: 'center', height: 40, fontSize: 13 }}
                  >
                    <strong>{c.percent}%</strong>
                    <div style={{ fontSize: 11 }}>
                      {c.filed}/{c.expected}
                    </div>
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function CountBars({ rows, colorFor, testId }: { rows: { key?: string; label: string; count: number }[]; colorFor: (label: string, key?: string) => string; testId: string }) {
  const max = Math.max(1, ...rows.map((r) => r.count))
  if (rows.every((r) => r.count === 0)) return <Typography.Text type="secondary">No filed documents in this selection.</Typography.Text>
  return (
    <Flex vertical gap={10}>
      {rows.map((r) => (
        <Flex key={r.key ?? r.label} gap={12} align="center" data-testid={testId}>
          <span style={{ width: 190, flexShrink: 0, fontSize: 13 }}>{r.label}</span>
          <div style={{ flex: '1 1 auto', minWidth: 60 }}>
            <Bar percent={(r.count / max) * 100} color={colorFor(r.label, r.key)} label={`${r.label}: ${r.count}`} />
          </div>
          <strong style={{ width: 40, textAlign: 'right' }}>{r.count}</strong>
        </Flex>
      ))}
    </Flex>
  )
}

const QC_COLOR: Record<string, string> = { Approved: INK.good, 'QC complete': INK.good, Rejected: INK.bad }
const TIMELY: Record<string, string> = { on_time: INK.good, late_10: INK.warn, late_20: INK.warn, late_more: INK.bad, no_date: '#8A97A8' }

function Expiring({ report }: { report: EtmfReport }) {
  if (report.expiring.length === 0) {
    return <Typography.Text type="secondary">No documents expired or expiring soon.</Typography.Text>
  }
  return (
    <Flex vertical>
      {report.expiring.map((e) => {
        const tone: ReportTone = e.state === 'expired' ? 'bad' : e.days <= 30 ? 'warn' : 'info'
        const label = e.state === 'expired' ? `Expired ${Math.abs(e.days)}d ago` : `In ${e.days} days`
        return (
          <Flex key={e.id} justify="space-between" align="center" gap={8} data-testid="expiring-row" style={{ padding: '8px 0', borderTop: '1px solid #EEF1F5' }}>
            <Flex vertical style={{ minWidth: 0 }}>
              <span style={{ fontWeight: 600 }}>{e.name}</span>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {e.protocol_number} · {e.where} · Expires {formatDay(e.expires_on)}
              </Typography.Text>
            </Flex>
            <ToneTag tone={toneStyle(tone, label)} />
          </Flex>
        )
      })}
    </Flex>
  )
}

export function EtmfTab({ filters, onFilters }: Props) {
  const { data, isLoading, isError, error, refetch } = useEtmfReport(filters)

  if (isError) {
    return (
      <Alert
        type="error"
        showIcon
        title="Could not load the eTMF report"
        description={error.message}
        action={<Button onClick={() => void refetch()}>Try again</Button>}
      />
    )
  }
  if (isLoading || !data) return <Skeleton active paragraph={{ rows: 10 }} />

  return (
    <Flex vertical gap={18}>
      <ReportToolbar
        filters={[
          {
            id: 'report-study',
            label: 'Study',
            ariaLabel: 'Filter by study',
            placeholder: 'All studies',
            value: filters.study_id,
            options: data.study_options,
            onChange: (id) => onFilters({ study_id: id, site_id: undefined }),
            width: 300,
          },
          {
            id: 'report-site',
            label: 'Site',
            ariaLabel: 'Filter by site',
            placeholder: 'All sites',
            value: filters.site_id,
            options: data.site_options,
            onChange: (id) => onFilters({ ...filters, site_id: id }),
            width: 260,
          },
        ]}
        source={data.source}
        sync="simpletrials"
        excelUrl={reportExportUrl('etmf', { study_id: filters.study_id, site_id: filters.site_id })}
      />
      <div className="print-only">
        <Typography.Title level={2} style={{ margin: 0 }}>
          eTMF report
        </Typography.Title>
        <Typography.Text type="secondary">
          {data.study_options.find((o) => o.id === filters.study_id)?.label ?? 'All studies'} · {formatDay(todayIso())}
        </Typography.Text>
      </div>
      {data.source.mode !== 'api' && <Alert type="warning" showIcon title="Demo data: SimpleTrials is not connected" />}
      {data.source.mode === 'api' && data.source.sandbox_only && (
        <Alert
          type="info"
          showIcon
          title="SimpleTrials sandbox study"
          description="Figures come from the sandbox study only. All studies appear once the Workspace (all studies) read-only key is enabled."
        />
      )}
      {!data.has_documents && (
        <Alert
          type="info"
          showIcon
          title="No eTMF documents from SimpleTrials yet"
          description="They appear after the next sync. If they still do not appear, the API key may not include eTMF access."
        />
      )}
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        Document metadata only: Avi.Intelligence never downloads eTMF files.
      </Typography.Text>

      <ReportTiles tiles={data.tiles} />

      <Flex gap={18} wrap>
        <ChartCard title="Completeness" rule={data.rules.completeness} flex="1 1 520px">
          <Flex gap={24} wrap align="center">
            <Donut c={data.overall} />
            <CompletenessRows rows={data.by_study} testId="study-completeness-row" empty="No studies in this selection." />
          </Flex>
        </ChartCard>
        <ChartCard title="Sites with the most missing documents" flex="1 1 380px">
          <CompletenessRows rows={data.sites_missing} testId="site-missing-row" empty="No missing site documents." />
        </ChartCard>
      </Flex>

      <ChartCard title="Completeness by site and TMF section" rule={data.rules.heat_map}>
        <SectionHeatMap report={data} />
      </ChartCard>

      <Flex gap={18} wrap>
        <ChartCard title="QC status" rule={data.rules.qc} flex="1 1 420px">
          <CountBars rows={data.qc} colorFor={(l) => QC_COLOR[l] ?? INK.info} testId="qc-row" />
        </ChartCard>
        <ChartCard title="Filing timeliness" rule={data.rules.timeliness} flex="1 1 420px">
          <CountBars rows={data.timeliness} colorFor={(_l, k) => TIMELY[k ?? ''] ?? INK.info} testId="timeliness-row" />
          {data.timeliness_measured > 0 && (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {data.timeliness_on_time} of {data.timeliness_measured} dated documents filed within the target.
            </Typography.Text>
          )}
        </ChartCard>
      </Flex>

      <ChartCard title="Expired and expiring documents" rule={data.rules.expiring}>
        <Expiring report={data} />
      </ChartCard>
    </Flex>
  )
}
