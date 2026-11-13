import { CloudSyncOutlined, SyncOutlined } from '@ant-design/icons'
import { Alert, App, Button, Card, Flex, Select, Skeleton, Typography } from 'antd'
import type { CSSProperties } from 'react'
import { Link, useSearchParams } from 'react-router'

import { useHasPermission, useOverview, useSyncAll } from '../../api/hooks'
import type { OverviewData, OverviewKpi, OverviewRow, OverviewSection } from '../../api/types'
import { formatDateTime } from '../../lib/format'
import { TONES } from '../../lib/studies'

const LONG_DATE = new Intl.DateTimeFormat('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })

function greeting(): string {
  const h = new Date().getHours()
  return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening'
}

/** A figure that opens the page with its detail. */
function Figure({ kpi, size = 'm', testId }: { kpi: OverviewKpi; size?: 'm' | 'l'; testId?: string }) {
  const tone = TONES[kpi.tone]
  const style: CSSProperties = {
    flex: '1 1 150px',
    minWidth: 0,
    borderRadius: 10,
    background: tone.background,
    border: `1px solid ${tone.border}`,
    color: tone.color,
    padding: size === 'l' ? '12px 14px' : '10px 12px',
    display: 'flex',
    flexDirection: 'column',
    gap: 2,
  }
  const body = (
    <>
      <span style={{ fontSize: size === 'l' ? 26 : 22, fontWeight: 700, lineHeight: 1.15 }}>{kpi.value}</span>
      <span style={{ fontSize: 13, fontWeight: 600 }}>{kpi.label}</span>
      {kpi.note && <span style={{ fontSize: 12, opacity: 0.85 }}>{kpi.note}</span>}
    </>
  )
  return kpi.link ? (
    <Link to={kpi.link} style={style} data-testid={testId}>
      {body}
    </Link>
  ) : (
    <div style={style} data-testid={testId}>
      {body}
    </div>
  )
}

function Line({ row, testId }: { row: OverviewRow; testId: string }) {
  const tone = TONES[row.tone]
  return (
    <Flex justify="space-between" align="center" gap={8} wrap style={{ padding: '9px 0', borderTop: '1px solid #EEF1F5' }} data-testid={testId}>
      <Flex vertical gap={2} style={{ minWidth: 0, flex: '1 1 260px' }}>
        {row.link ? (
          <Link to={row.link} style={{ fontWeight: 600, color: '#14223A' }}>
            {row.label}
          </Link>
        ) : (
          <span style={{ fontWeight: 600 }}>{row.label}</span>
        )}
        {row.detail && <Typography.Text type="secondary" style={{ fontSize: 12 }}>{row.detail}</Typography.Text>}
      </Flex>
      {row.chip && (
        <span
          style={{
            fontSize: 12,
            fontWeight: 600,
            borderRadius: 999,
            padding: '2px 10px',
            color: tone.color,
            background: tone.background,
            border: `1px solid ${tone.border}`,
            whiteSpace: 'nowrap',
          }}
        >
          {row.chip}
        </span>
      )}
    </Flex>
  )
}

function SectionCard({ section }: { section: OverviewSection }) {
  const wide = section.kpis.length >= 4 || section.key === 'my_sites' || section.key === 'connectors'
  return (
    <Card
      size="small"
      data-testid={`overview-section-${section.key}`}
      style={{ gridColumn: wide ? '1 / -1' : undefined }}
      styles={{ body: { padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 12 } }}
    >
      <Flex justify="space-between" align="baseline" wrap gap={8}>
        <Typography.Title level={4} style={{ margin: 0, fontSize: 16 }}>
          {section.title}{' '}
          {section.source && (
            <Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 400 }}>
              {section.source}
            </Typography.Text>
          )}
        </Typography.Title>
        {section.link && (
          <Link to={section.link} style={{ fontSize: 13, fontWeight: 600 }}>
            {section.link_label ?? 'Open'}
          </Link>
        )}
      </Flex>
      {section.notice && <Alert type="info" showIcon title={section.notice} />}
      {section.kpis.length > 0 && (
        <Flex gap={10} wrap>
          {section.kpis.map((k) => (
            <Figure key={k.label} kpi={k} />
          ))}
        </Flex>
      )}
      {section.rows.length > 0 ? (
        <div>
          {section.rows.map((r, i) => (
            <Line key={`${r.label}-${i}`} row={r} testId="overview-row" />
          ))}
        </div>
      ) : (
        section.empty &&
        !section.notice && <Typography.Text type="secondary">{section.empty}</Typography.Text>
      )}
    </Card>
  )
}

function Freshness({ data }: { data: OverviewData }) {
  const { message } = App.useApp()
  const canSyncStudies = useHasPermission('study.sync')
  const canSyncViedoc = useHasPermission('dm.sync')
  const sync = useSyncAll()
  const hasViedoc = data.sources.some((s) => s.name === 'Viedoc')
  return (
    <Flex
      align="center"
      gap={12}
      wrap
      role="status"
      style={{ background: '#FFFFFF', border: '1px solid #DCE2EA', borderRadius: 10, padding: '8px 12px' }}
    >
      {data.sources.map((s) => (
        <Typography.Text key={s.name} type="secondary" style={{ fontSize: 12 }} data-testid="overview-source">
          <CloudSyncOutlined style={{ color: s.ok ? '#0F5B36' : '#8A1C12' }} /> <strong style={{ color: '#14223A' }}>{s.name}</strong>{' '}
          {s.ok ? (s.as_of ? formatDateTime(s.as_of) : 'not synced yet') : 'last sync failed'}
        </Typography.Text>
      ))}
      <Button
        type="primary"
        icon={<SyncOutlined />}
        loading={sync.isPending}
        onClick={() =>
          sync.mutate(
            { studies: canSyncStudies, viedoc: hasViedoc && canSyncViedoc },
            {
              onSuccess: (failed) =>
                failed ? void message.warning(`Synced, but ${failed} source${failed === 1 ? '' : 's'} could not be reached`) : void message.success('All sources synced'),
            },
          )
        }
      >
        Sync all
      </Button>
    </Flex>
  )
}

/** The role-based home page: what needs you today, then the sections that matter for your role. */
export function OverviewPage() {
  const [params, setParams] = useSearchParams()
  const view = params.get('view') ?? undefined
  const { data, isLoading, isError, error, refetch } = useOverview(view)

  if (isError) {
    return (
      <Alert
        type="error"
        showIcon
        title="Could not load the Overview"
        description={error.message}
        action={<Button onClick={() => void refetch()}>Try again</Button>}
      />
    )
  }
  if (isLoading || !data) return <Skeleton active paragraph={{ rows: 12 }} />

  return (
    <Flex vertical gap={18} style={{ maxWidth: 1200 }}>
      <Flex justify="space-between" align="flex-end" wrap gap={12}>
        <Flex vertical gap={2}>
          <Typography.Text type="secondary" style={{ fontSize: 13 }}>
            {LONG_DATE.format(new Date())} · {data.view_label}
          </Typography.Text>
          <Typography.Title level={2} style={{ margin: 0 }}>
            {greeting()}
          </Typography.Title>
          <Typography.Text type="secondary">{data.purpose}</Typography.Text>
        </Flex>
        <Flex gap={10} wrap align="center">
          {data.views.length > 1 && (
            <Select
              aria-label="View the Overview as"
              value={data.view}
              onChange={(v: string) => {
                const next = new URLSearchParams(params)
                next.set('view', v)
                setParams(next, { replace: true })
              }}
              options={data.views.map((v) => ({ value: v.id, label: `View as ${v.label}` }))}
              style={{ minWidth: 260 }}
              popupMatchSelectWidth={false}
            />
          )}
          <Freshness data={data} />
        </Flex>
      </Flex>

      <Card
        size="small"
        data-testid="overview-attention"
        styles={{ body: { padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 12 } }}
      >
        <Flex justify="space-between" align="baseline" wrap gap={8}>
          <Typography.Title level={4} style={{ margin: 0, fontSize: 16 }}>
            Needs your attention
          </Typography.Title>
          <Link to="/tasks" style={{ fontSize: 13, fontWeight: 600 }}>
            All my tasks
          </Link>
        </Flex>
        <Flex gap={10} wrap>
          {data.attention.counts.map((k) => (
            <Figure key={k.label} kpi={k} size="l" testId="overview-attention-count" />
          ))}
        </Flex>
        {data.attention.items.length > 0 ? (
          <div>
            {data.attention.items.map((r, i) => (
              <Line key={`${r.label}-${i}`} row={r} testId="overview-task" />
            ))}
          </div>
        ) : (
          <Typography.Text type="secondary">Nothing assigned to you needs attention today.</Typography.Text>
        )}
      </Card>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 440px), 1fr))', gap: 14 }}>
        {data.sections.map((s) => (
          <SectionCard key={s.key} section={s} />
        ))}
      </div>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        Every figure comes from the same rules as its report and opens the page with the detail. Nothing is estimated and
        nothing is written by AI.
      </Typography.Text>
    </Flex>
  )
}
