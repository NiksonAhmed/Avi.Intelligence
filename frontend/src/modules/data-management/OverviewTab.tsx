import { Alert, Button, Card, Flex, Progress, Skeleton, Table, Typography } from 'antd'

import { TONES } from '../../lib/studies'
import type { DmOverview, DmStatus } from './api'
import { useDmOverview } from './api'

interface Props {
  scope: string
  /** Open the SDV tab (optionally for one site). */
  onOpenSdv?: (site?: string) => void
  status: DmStatus
  /** Open the Queries tab with these filters. */
  onOpen: (filters: Record<string, string | undefined>) => void
}

const INK = { good: '#1E7F4F', info: '#1F4E8C', warn: '#B26B00', bad: '#B42318', neutral: '#0A1F3C' }

/** Headline tiles; keys in `percentKeys` are shown with a % sign. */
export function Tiles({
  tiles,
  percentKeys = [],
  testIdPrefix = 'dm-tile',
}: {
  tiles: DmOverview['tiles']
  percentKeys?: string[]
  testIdPrefix?: string
}) {
  return (
    <Flex gap={14} wrap>
      {tiles.map((t) => (
        <Card key={t.key} size="small" style={{ flex: '1 1 170px', minWidth: 0 }} styles={{ body: { padding: '14px 18px' } }}>
          <Flex vertical gap={4}>
            <Typography.Text type="secondary" style={{ fontSize: 13, fontWeight: 600 }}>
              {t.label.replace(' (%)', '')}
            </Typography.Text>
            <span data-testid={`${testIdPrefix}-${t.key}`} style={{ fontSize: 28, fontWeight: 700, lineHeight: 1.15, color: INK[t.tone] }}>
              {t.value}
              {percentKeys.includes(t.key) ? '%' : ''}
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

function CountLink({ n, onClick, label, tone }: { n: number; onClick: () => void; label: string; tone?: keyof typeof TONES }) {
  if (!n) return <Typography.Text type="secondary">0</Typography.Text>
  return (
    <Button type="link" size="small" onClick={onClick} aria-label={label} style={{ padding: 0, fontWeight: 700, color: tone ? TONES[tone].color : undefined }}>
      {n}
    </Button>
  )
}

export function OverviewTab({ scope, status, onOpen, onOpenSdv }: Props) {
  const { data, isLoading, isError, error } = useDmOverview(scope)
  if (isError) return <Alert type="error" showIcon title="Could not load the overview" description={error.message} />
  if (isLoading || !data) return <Skeleton active paragraph={{ rows: 8 }} />
  const maxBucket = Math.max(1, ...data.ageing.map((b) => b.open_at_site + b.awaiting_approval))
  // With several studies, a site is "study:site" (the same site code can exist in two studies).
  const siteId = (r: DmOverview['sites'][number]) => (data.multi ? `${r.connection}:${r.site_code}` : r.site_code)
  return (
    <Flex vertical gap={18}>
      <Tiles tiles={data.tiles} percentKeys={['sdv']} />

      <Card
        size="small"
        title="SDV completed vs required"
        extra={
          onOpenSdv && (
            <Button type="link" size="small" onClick={() => onOpenSdv()}>
              Open SDV
            </Button>
          )
        }
      >
        {data.sdv.required === 0 ? (
          <Typography.Text type="secondary">No fields are set up for SDV in Viedoc for this selection.</Typography.Text>
        ) : (
          <Flex vertical gap={12}>
            <Flex align="baseline" gap={10} wrap>
              <span data-testid="dm-sdv-figure" style={{ fontSize: 26, fontWeight: 700 }}>
                {data.sdv.done} of {data.sdv.required}
              </span>
              <Typography.Text type="secondary">
                fields verified ({data.sdv.percent ?? 0}%) · {data.sdv.forms_complete} of {data.sdv.forms_total} forms fully verified
              </Typography.Text>
            </Flex>
            <Progress percent={data.sdv.percent ?? 0} showInfo={false} strokeColor={INK.info} aria-label="SDV completed" />
            {data.sites
              .filter((r) => r.sdv_required > 0)
              .map((r) => {
                const pct = Math.round((r.sdv_done / r.sdv_required) * 1000) / 10
                const site = data.multi ? `${r.connection}:${r.site_code}` : r.site_code
                return (
                  <Flex key={`${r.connection}:${r.site_code}`} align="center" gap={10} data-testid="dm-sdv-overview-site">
                    <Button type="link" size="small" style={{ padding: 0, width: 220, justifyContent: 'flex-start' }} onClick={() => onOpenSdv?.(site)}>
                      {data.multi ? `${r.study_code} · ` : ''}
                      {r.site_code} · {r.site_name}
                    </Button>
                    <Progress percent={pct} size="small" showInfo={false} strokeColor={pct >= 100 ? INK.good : pct >= 50 ? INK.info : INK.warn} style={{ flex: 1, margin: 0 }} />
                    <span style={{ width: 130, textAlign: 'right', fontSize: 12 }}>
                      {r.sdv_done} / {r.sdv_required} ({pct}%)
                    </span>
                  </Flex>
                )
              })}
          </Flex>
        )}
      </Card>

      <Card size="small" title="By site" styles={{ body: { padding: 0 } }}>
        <Table
          size="small"
          rowKey={(r) => `${r.connection}:${r.site_code}`}
          pagination={false}
          dataSource={data.sites}
          scroll={{ x: 760 }}
          onRow={() => ({ 'data-testid': 'dm-site-row' }) as React.HTMLAttributes<HTMLElement>}
          columns={[
            ...(data.multi ? [{ title: 'Study', dataIndex: 'study_code', key: 'study' }] : []),
            { title: 'Site', key: 'site', render: (_, r) => <strong>{r.site_code} · {r.site_name}</strong> },
            {
              title: 'Open at site',
              key: 'open',
              align: 'right',
              render: (_, r) => (
                <CountLink n={r.open_at_site} label={`Open at site ${r.site_code}`} onClick={() => onOpen({ site: siteId(r), view: 'open' })} />
              ),
            },
            {
              title: 'Awaiting approval',
              key: 'awaiting',
              align: 'right',
              render: (_, r) => (
                <CountLink n={r.awaiting_approval} label={`Awaiting approval ${r.site_code}`} onClick={() => onOpen({ site: siteId(r), view: 'awaiting' })} />
              ),
            },
            {
              title: 'Overdue',
              key: 'red',
              align: 'right',
              render: (_, r) => (
                <CountLink n={r.overdue} tone="bad" label={`Overdue ${r.site_code}`} onClick={() => onOpen({ site: siteId(r), view: 'overdue' })} />
              ),
            },
            { title: 'Oldest open (days)', dataIndex: 'oldest_days', align: 'right', render: (v: number | null) => v ?? '—' },
            { title: 'Unconfirmed missing data', dataIndex: 'missing_items', align: 'right' },
            { title: 'Pending forms', dataIndex: 'pending_forms', align: 'right' },
            {
              title: 'SDV',
              key: 'sdv',
              align: 'right',
              render: (_, r) => (r.sdv_required ? `${Math.round((r.sdv_done / r.sdv_required) * 100)}%` : '—'),
            },
          ]}
        />
      </Card>

      <Flex gap={18} wrap>
        <Card size="small" title="Age of queries not yet closed" style={{ flex: '1 1 420px', minWidth: 0 }}>
          <Flex vertical gap={10}>
            {data.ageing.map((b) => {
              const total = b.open_at_site + b.awaiting_approval
              return (
                <Flex key={b.label} gap={12} align="center" data-testid="dm-ageing-row">
                  <span style={{ width: 70, flexShrink: 0 }}>{b.label} days</span>
                  <div
                    role="img"
                    aria-label={`${b.label} days: ${b.open_at_site} open at site, ${b.awaiting_approval} awaiting approval`}
                    style={{ flex: '1 1 auto', display: 'flex', height: 14, background: '#EEF1F5', borderRadius: 3, overflow: 'hidden' }}
                  >
                    <div style={{ width: `${(b.open_at_site / maxBucket) * 100}%`, background: INK.info }} />
                    <div style={{ width: `${(b.awaiting_approval / maxBucket) * 100}%`, background: INK.warn }} />
                  </div>
                  <strong style={{ width: 32, textAlign: 'right' }}>{total}</strong>
                </Flex>
              )
            })}
            <Flex gap={14} style={{ fontSize: 12, color: '#3E4C5E' }} aria-hidden>
              <span>
                <span style={{ display: 'inline-block', width: 10, height: 10, background: INK.info, marginRight: 6 }} />
                Open at site
              </span>
              <span>
                <span style={{ display: 'inline-block', width: 10, height: 10, background: INK.warn, marginRight: 6 }} />
                Awaiting approval
              </span>
            </Flex>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {status.rules.ageing}
            </Typography.Text>
          </Flex>
        </Card>
        <Card size="small" title="Queries not yet closed, by form" style={{ flex: '1 1 320px', minWidth: 0 }}>
          {data.forms.length === 0 ? (
            <Typography.Text type="secondary">No open queries.</Typography.Text>
          ) : (
            <Flex vertical gap={6}>
              {data.forms.map((f) => (
                <Flex key={f.form} justify="space-between" style={{ borderBottom: '1px solid #EEF1F5', padding: '4px 0' }}>
                  <span>{f.form}</span>
                  <strong>{f.open}</strong>
                </Flex>
              ))}
            </Flex>
          )}
        </Card>
      </Flex>

      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        {status.rules.clocks} {status.rules.targets} Targets: sites {status.site_answer_days} working days, approval{' '}
        {status.approval_days} working days. {status.rules.missing} {status.rules.source}
      </Typography.Text>
    </Flex>
  )
}
