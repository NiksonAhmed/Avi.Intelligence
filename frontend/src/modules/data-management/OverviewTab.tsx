import { Alert, Button, Card, Flex, Skeleton, Table, Typography } from 'antd'

import { TONES } from '../../lib/studies'
import type { DmOverview, DmStatus } from './api'
import { useDmOverview } from './api'

interface Props {
  scope: string
  status: DmStatus
  /** Open the Queries tab with these filters. */
  onOpen: (filters: Record<string, string | undefined>) => void
}

const INK = { good: '#1E7F4F', info: '#1F4E8C', warn: '#B26B00', bad: '#B42318', neutral: '#0A1F3C' }

function Tiles({ tiles }: { tiles: DmOverview['tiles'] }) {
  return (
    <Flex gap={14} wrap>
      {tiles.map((t) => (
        <Card key={t.key} size="small" style={{ flex: '1 1 190px', minWidth: 0 }} styles={{ body: { padding: '14px 18px' } }}>
          <Flex vertical gap={4}>
            <Typography.Text type="secondary" style={{ fontSize: 13, fontWeight: 600 }}>
              {t.label}
            </Typography.Text>
            <span data-testid={`dm-tile-${t.key}`} style={{ fontSize: 28, fontWeight: 700, lineHeight: 1.15, color: INK[t.tone] }}>
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

function CountLink({ n, onClick, label, tone }: { n: number; onClick: () => void; label: string; tone?: keyof typeof TONES }) {
  if (!n) return <Typography.Text type="secondary">0</Typography.Text>
  return (
    <Button type="link" size="small" onClick={onClick} aria-label={label} style={{ padding: 0, fontWeight: 700, color: tone ? TONES[tone].color : undefined }}>
      {n}
    </Button>
  )
}

export function OverviewTab({ scope, status, onOpen }: Props) {
  const { data, isLoading, isError, error } = useDmOverview(scope)
  if (isError) return <Alert type="error" showIcon title="Could not load the overview" description={error.message} />
  if (isLoading || !data) return <Skeleton active paragraph={{ rows: 8 }} />
  const maxBucket = Math.max(1, ...data.ageing.map((b) => b.open_at_site + b.awaiting_approval))
  // With several studies, a site is "study:site" (the same site code can exist in two studies).
  const siteId = (r: DmOverview['sites'][number]) => (data.multi ? `${r.connection}:${r.site_code}` : r.site_code)
  return (
    <Flex vertical gap={18}>
      <Tiles tiles={data.tiles} />

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
