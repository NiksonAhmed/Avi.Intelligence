import { FileExcelOutlined, FilePdfOutlined, SyncOutlined } from '@ant-design/icons'
import { Alert, App, Button, Card, Flex, Skeleton, Table, Tag, Typography } from 'antd'
import type { CSSProperties, HTMLAttributes } from 'react'
import { useSearchParams } from 'react-router'

import { conferencesExportUrl } from '../../api/client'
import { useConferences, useRefreshConferences } from '../../api/hooks'
import type { AvionRole, Conference, ConferencesReport } from '../../api/types'
import worldMap from '../../assets/world-map.svg'
import { PageHeader } from '../../components/PageHeader'
import { formatDateTime, formatDay } from '../../lib/format'
import { ReportTiles } from '../reports/ReportParts'
import './ConferencesPage.css'

const ROLES: AvionRole[] = ['Exhibiting', 'Speaking', 'Attending', 'Considering']
const ROLE_COLOUR: Record<AvionRole, string> = {
  Exhibiting: '#4F8BFF',
  Speaking: '#FF8A50',
  Attending: '#2EE6C5',
  Considering: '#A9B4D0',
}
const PAST = '#5D6A8A'
// The map image is Natural Earth land (public domain), equirectangular, 180°W–180°E and 83°N–58°S.
const fx = (lon: number) => (lon + 180) / 360
const fy = (lat: number) => (83 - lat) / 141
const pct = (v: number) => `${(v * 100).toFixed(2)}%`
const OCEANS = [
  { label: 'PACIFIC\nOCEAN', lon: -140, lat: 10 },
  { label: 'ATLANTIC\nOCEAN', lon: -38, lat: 22 },
  { label: 'INDIAN\nOCEAN', lon: 78, lat: -22 },
  { label: 'PACIFIC\nOCEAN', lon: 165, lat: 15 },
]

function colourOf(c: Conference): string {
  return c.past ? PAST : ROLE_COLOUR[c.role]
}

function when(c: Conference): string {
  if (c.past) return 'Done'
  return c.days_until > 0 ? `In ${c.days_until} days` : 'On now'
}

function dates(c: Conference): string {
  return c.ends_on !== c.starts_on ? `${formatDay(c.starts_on)} – ${formatDay(c.ends_on)}` : formatDay(c.starts_on)
}

/** Curved arcs between consecutive conferences, bowed upwards like flight paths. */
function arcs(points: [number, number][]): string {
  return points
    .slice(1)
    .map((b, i) => {
      const a = points[i]!
      const dist = Math.hypot(b[0] - a[0], b[1] - a[1])
      const cx = (a[0] + b[0]) / 2
      const cy = Math.max(4, (a[1] + b[1]) / 2 - dist * 0.28)
      return `M${a[0].toFixed(1)},${a[1].toFixed(1)} Q${cx.toFixed(1)},${cy.toFixed(1)} ${b[0].toFixed(1)},${b[1].toFixed(1)}`
    })
    .join(' ')
}

function Chip({ on, label, dot, onClick }: { on: boolean; label: string; dot?: string; onClick: () => void }) {
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={onClick}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        minHeight: 34,
        padding: '0 12px',
        borderRadius: 999,
        border: `1px solid ${on ? '#FFFFFF' : '#2C3F72'}`,
        background: on ? '#FFFFFF' : 'transparent',
        color: on ? '#0B1446' : '#FFFFFF',
        font: '600 13px inherit',
        cursor: 'pointer',
      }}
    >
      {dot && <span aria-hidden="true" style={{ width: 10, height: 10, borderRadius: '50%', background: dot }} />}
      {label}
    </button>
  )
}

function WorldMap({
  report,
  selected,
  onSelect,
}: {
  report: ConferencesReport
  selected: Conference | undefined
  onSelect: (id: string) => void
}) {
  const placed = report.conferences.filter((c) => c.lat !== null && c.lon !== null)
  const path = arcs(placed.map((c) => [fx(c.lon!) * 1000, fy(c.lat!) * 391.7]))
  return (
    <div
      role="img"
      aria-label={`World map with ${placed.length} conferences in ${report.year}`}
      data-testid="conference-map"
      style={{
        position: 'relative',
        width: '100%',
        aspectRatio: '360 / 141',
        background: 'radial-gradient(ellipse at 50% 35%, #1A2A6C 0%, #0C1446 55%, #070B2A 100%)',
        borderRadius: 12,
        overflow: 'hidden',
      }}
    >
      <img
        src={worldMap}
        alt=""
        style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none', filter: 'drop-shadow(0 0 12px rgba(70,160,255,0.45))' }}
      />
      {OCEANS.map((o, i) => (
        <span
          key={i}
          aria-hidden="true"
          style={{
            position: 'absolute',
            left: pct(fx(o.lon)),
            top: pct(fy(o.lat)),
            transform: 'translate(-50%, -50%)',
            pointerEvents: 'none',
            fontSize: 10,
            fontWeight: 600,
            letterSpacing: '0.28em',
            color: '#7F93D6',
            textAlign: 'center',
            whiteSpace: 'pre-line',
            lineHeight: 1.5,
          }}
        >
          {o.label}
        </span>
      ))}
      {path && (
        <svg aria-hidden="true" viewBox="0 0 1000 391.7" preserveAspectRatio="none" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }}>
          <path d={path} fill="none" stroke="#FFFFFF" strokeOpacity={0.18} strokeWidth={5} vectorEffect="non-scaling-stroke" />
          <path className="conf-route" d={path} fill="none" stroke="#FFFFFF" strokeOpacity={0.8} strokeWidth={1.3} strokeDasharray="5 7" vectorEffect="non-scaling-stroke" />
        </svg>
      )}
      {placed.map((c) => {
        const colour = colourOf(c)
        const on = selected?.id === c.id
        const at: CSSProperties = { position: 'absolute', left: pct(fx(c.lon!)), top: pct(fy(c.lat!)) }
        return (
          <span key={c.id}>
            <span
              aria-hidden="true"
              style={{ ...at, pointerEvents: 'none', width: 34, height: 34, borderRadius: '50%', transform: 'translate(-50%, -50%)', background: `radial-gradient(circle, ${colour}AA 0%, transparent 70%)` }}
            />
            {report.next_id === c.id && (
              <span
                className="conf-ring"
                aria-hidden="true"
                style={{ ...at, pointerEvents: 'none', width: 18, height: 18, borderRadius: '50%', border: '2px solid #FFFFFF', boxSizing: 'border-box' }}
              />
            )}
            <button
              type="button"
              className="conf-pin"
              data-testid="conference-pin"
              aria-label={`${c.name}, ${c.city ?? ''}, ${formatDay(c.starts_on)} (${c.role})`}
              aria-pressed={on}
              onClick={() => onSelect(c.id)}
              style={{
                ...at,
                transform: 'translate(-50%, -50%)',
                width: on ? 16 : 11,
                height: on ? 16 : 11,
                borderRadius: '50%',
                background: '#FFFFFF',
                border: 0,
                padding: 0,
                cursor: 'pointer',
                boxShadow: `0 0 0 3px ${colour}, 0 0 14px 5px ${colour}${on ? ', 0 0 0 7px rgba(255,255,255,0.35)' : ''}`,
              }}
            />
            <span
              aria-hidden="true"
              style={{
                ...at,
                pointerEvents: 'none',
                transform: 'translate(14px, -50%)',
                fontSize: 11,
                fontWeight: 600,
                color: '#FFFFFF',
                background: 'rgba(7,11,42,0.72)',
                border: `1px solid ${on ? '#FFFFFF' : `${colour}66`}`,
                borderRadius: 6,
                padding: '2px 7px',
                whiteSpace: 'nowrap',
              }}
            >
              {c.city}
            </span>
          </span>
        )
      })}
    </div>
  )
}

function Details({ c, canSeeCost }: { c: Conference; canSeeCost: boolean }) {
  const colour = colourOf(c)
  const rows: [string, string][] = [
    ['Who is going', c.team ?? '—'],
    ['Booth', c.booth ?? '—'],
    ['Register by', c.register_by ? formatDay(c.register_by) : '—'],
    ['Notes', c.notes ?? '—'],
  ]
  if (canSeeCost) rows.push(['Cost', c.cost !== null ? `${c.cost.toLocaleString()} ${c.currency ?? ''}`.trim() : '—'])
  return (
    <Card data-testid="conference-details" style={{ borderTop: `4px solid ${colour}` }} styles={{ body: { display: 'flex', flexDirection: 'column', gap: 8 } }}>
      <Tag style={{ alignSelf: 'flex-start', background: colour, color: '#0B1446', border: 0, fontWeight: 700 }}>
        {c.role}
        {c.past ? ' · done' : ''}
      </Tag>
      <Typography.Title level={4} style={{ margin: 0 }}>
        {c.name}
      </Typography.Title>
      <Typography.Text>{[c.city, c.country].filter(Boolean).join(', ') || 'Location not recorded'}</Typography.Text>
      <Typography.Text strong>
        {dates(c)} <Typography.Text type="secondary">· {when(c)}</Typography.Text>
      </Typography.Text>
      {c.register_soon && <Alert type="warning" showIcon title={`Registration closes ${formatDay(c.register_by!)}`} />}
      <dl style={{ margin: 0, display: 'grid', gridTemplateColumns: 'max-content 1fr', gap: '6px 12px', fontSize: 13 }}>
        {rows.map(([k, v]) => (
          <div key={k} style={{ display: 'contents' }}>
            <dt style={{ color: '#5B6B82' }}>{k}</dt>
            <dd style={{ margin: 0 }}>{v}</dd>
          </div>
        ))}
      </dl>
      <Flex gap={12} wrap>
        {c.source_url && (
          <a href={c.source_url} target="_blank" rel="noreferrer">
            Open in SharePoint
          </a>
        )}
        {c.website && (
          <a href={c.website} target="_blank" rel="noreferrer">
            Conference website
          </a>
        )}
      </Flex>
    </Card>
  )
}

/** Conferences: where Avion's BD team is going, from their SharePoint list (read-only). */
export function ConferencesPage() {
  const { message } = App.useApp()
  const [params, setParams] = useSearchParams()
  const year = params.get('year') ? Number(params.get('year')) : undefined
  const role = params.get('role') ?? undefined
  const picked = params.get('id') ?? undefined
  const { data, isLoading, isError, error, refetch } = useConferences({ year, role })
  const refresh = useRefreshConferences()

  const set = (changes: Record<string, string | undefined>) => {
    const next = new URLSearchParams(params)
    for (const [k, v] of Object.entries(changes)) {
      if (v) next.set(k, v)
      else next.delete(k)
    }
    setParams(next, { replace: true })
  }

  if (isError) {
    return (
      <Alert
        type="error"
        showIcon
        title="Could not load conferences"
        description={error.message}
        action={<Button onClick={() => void refetch()}>Try again</Button>}
      />
    )
  }
  if (isLoading || !data) return <Skeleton active paragraph={{ rows: 12 }} />

  const selected = data.conferences.find((c) => c.id === picked) ?? data.conferences.find((c) => c.id === data.next_id) ?? data.conferences[0]
  const exportUrl = conferencesExportUrl({ year: String(data.year), role })

  return (
    <Flex vertical gap={16}>
      <PageHeader
        title="Where Avion is going"
        subtitle="Conferences the BD team plans to attend, from their SharePoint list. Click a pin for the details."
        extra={
          <Flex gap={8} wrap align="center" className="no-print">
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {data.source.mode === 'sharepoint'
                ? `SharePoint · BD conferences · ${data.source.fetched_at ? formatDateTime(data.source.fetched_at) : 'not read yet'}`
                : 'Demo data'}
            </Typography.Text>
            <Button
              icon={<SyncOutlined />}
              loading={refresh.isPending}
              onClick={() =>
                refresh.mutate(undefined, {
                  onSuccess: () => void message.success('Conferences synced'),
                  onError: (e) => void message.error(e.message),
                })
              }
            >
              Sync now
            </Button>
            <Button icon={<FileExcelOutlined />} href={exportUrl}>
              Excel
            </Button>
            <Button icon={<FilePdfOutlined />} onClick={() => window.print()}>
              PDF
            </Button>
          </Flex>
        }
      />
      {data.source.mode === 'demo' && (
        <Alert
          type="warning"
          showIcon
          title="Demo conferences: the BD team's SharePoint list is not connected yet"
          description={`${data.source.reason ?? ''} These conferences are made up and are not Avion's plans.`}
        />
      )}

      <ReportTiles tiles={data.tiles} />

      <section aria-label="World map" style={{ background: '#070B2A', borderRadius: 16, padding: 14, display: 'flex', flexDirection: 'column', gap: 12 }}>
        <Flex gap={8} wrap align="center" className="no-print">
          {data.years.map((y) => (
            <Chip key={y} on={y === data.year} label={String(y)} onClick={() => set({ year: String(y), id: undefined })} />
          ))}
          <span style={{ width: 1, height: 24, background: '#2C3F72' }} />
          <Chip on={!role} label="All" onClick={() => set({ role: undefined, id: undefined })} />
          {ROLES.map((r) => (
            <Chip key={r} on={role === r} label={r} dot={ROLE_COLOUR[r]} onClick={() => set({ role: r, id: undefined })} />
          ))}
        </Flex>
        <WorldMap report={data} selected={selected} onSelect={(id) => set({ id })} />
        <Flex gap={16} wrap style={{ fontSize: 12, color: '#C9D5E6' }}>
          {[...ROLES.map((r) => [r, ROLE_COLOUR[r]] as const), ['Already happened', PAST] as const].map(([label, colour]) => (
            <span key={label} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span aria-hidden="true" style={{ width: 10, height: 10, borderRadius: '50%', background: '#FFFFFF', boxShadow: `0 0 0 3px ${colour}, 0 0 10px 3px ${colour}` }} />
              {label}
            </span>
          ))}
          <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span aria-hidden="true" style={{ width: 20, borderTop: '2px dashed #FFFFFF', opacity: 0.8 }} />
            The year&apos;s route, in date order
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span aria-hidden="true" style={{ width: 12, height: 12, borderRadius: '50%', border: '2px solid #FFFFFF', boxSizing: 'border-box' }} />
            Next conference (pulses)
          </span>
          {data.not_on_map > 0 && <span>{data.not_on_map} not on the map (city not known yet)</span>}
        </Flex>
      </section>

      <Flex gap={14} wrap align="flex-start">
        <div style={{ flex: '1 1 320px', minWidth: 0 }}>
          {selected ? (
            <Details c={selected} canSeeCost={data.can_see_cost} />
          ) : (
            <Card>
              <Typography.Text type="secondary">No conferences in this selection.</Typography.Text>
            </Card>
          )}
        </div>
        <Card title={`All conferences in ${data.year} (${data.conferences.length})`} style={{ flex: '2 1 560px', minWidth: 0 }}>
          <Table<Conference>
            size="small"
            rowKey="id"
            dataSource={data.conferences}
            pagination={false}
            scroll={{ x: 760 }}
            locale={{ emptyText: 'No conferences in this selection.' }}
            onRow={(c) =>
              ({
                'data-testid': 'conference-row',
                onClick: () => set({ id: c.id }),
                style: { cursor: 'pointer', background: c.id === selected?.id ? '#EEF3FB' : undefined },
              }) as HTMLAttributes<HTMLElement>
            }
            columns={[
              { title: 'Dates', key: 'dates', width: 170, render: (_, c) => <strong>{dates(c)}</strong> },
              { title: 'Conference', dataIndex: 'name' },
              { title: 'Where', key: 'where', width: 170, render: (_, c) => [c.city, c.country].filter(Boolean).join(', ') || '—' },
              {
                title: "Avion's role",
                key: 'role',
                width: 130,
                render: (_, c) => (
                  <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span aria-hidden="true" style={{ width: 10, height: 10, borderRadius: '50%', background: colourOf(c) }} />
                    {c.role}
                  </span>
                ),
              },
              {
                title: 'When',
                key: 'when',
                width: 120,
                render: (_, c) => (
                  <Flex vertical gap={0}>
                    <span>{when(c)}</span>
                    {c.register_soon && <Typography.Text type="warning" style={{ fontSize: 12 }}>Register soon</Typography.Text>}
                  </Flex>
                ),
              },
            ]}
          />
        </Card>
      </Flex>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        {data.rules.source} Map outlines: Natural Earth (public domain).
      </Typography.Text>
    </Flex>
  )
}
