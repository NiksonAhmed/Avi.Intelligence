import { FileExcelOutlined, FilePdfOutlined, SyncOutlined } from '@ant-design/icons'
import { Alert, App, Button, Card, Drawer, Flex, Skeleton, Table, Tag, Tooltip, Typography } from 'antd'
import type { CSSProperties } from 'react'
import { useSearchParams } from 'react-router'

import { siteValidationExportUrl } from '../../api/client'
import { useRefreshSiteValidation, useSiteDetail, useSiteValidation } from '../../api/hooks'
import type { ScanStatus, SiteDetail, SitePin, SiteValidationReport, ValidationRow, ValidationStatus } from '../../api/types'
import { PageHeader } from '../../components/PageHeader'
import { formatDateTime, formatDay } from '../../lib/format'
import { MoreDetail, ReportTiles, RuleInfo } from '../reports/ReportParts'
import { AustraliaMap } from './SiteMap'
import type { MapPin } from './SiteMap'
import './SiteValidationPage.css'

const STATUS: Record<ValidationStatus, { label: string; colour: string; bg: string; fg: string; symbol: string }> = {
  overdue: { label: 'Overdue', colour: '#FF5C5C', bg: '#FDE8E6', fg: '#A1210F', symbol: '✕' },
  files_missing: { label: 'Files missing', colour: '#FF8A50', bg: '#FFEEDD', fg: '#9A3A05', symbol: '!' },
  due_soon: { label: 'Due soon', colour: '#FFC24B', bg: '#FDF0D5', fg: '#7A4A06', symbol: '!' },
  booked: { label: 'Booked', colour: '#8FA3FF', bg: '#ECEFFD', fg: '#3442A3', symbol: '○' },
  in_date: { label: 'In date', colour: '#2EE6A0', bg: '#DCF5E7', fg: '#14633A', symbol: '✓' },
  none: { label: 'Nothing validated', colour: '#A9B4D0', bg: '#EEF0F4', fg: '#3D4757', symbol: '–' },
}
const SCAN: Record<ScanStatus, { bg: string; fg: string }> = {
  Booked: { bg: '#ECEFFD', fg: '#3442A3' },
  Scanned: { bg: '#E6F0FF', fg: '#0B4FB3' },
  'Submitted to core lab': { bg: '#FDF0D5', fg: '#7A4A06' },
  Passed: { bg: '#DCF5E7', fg: '#14633A' },
  Failed: { bg: '#FDE8E6', fg: '#A1210F' },
}
function StatusTag({ status }: { status: ValidationStatus }) {
  const s = STATUS[status]
  return <Tag style={{ background: s.bg, color: s.fg, border: 0, fontWeight: 600 }}>{s.label}</Tag>
}

function Chip({ on, label, onClick }: { on: boolean; label: string; onClick: () => void }) {
  return (
    <button type="button" aria-pressed={on} onClick={onClick} className={`sv-chip${on ? ' on' : ''}`}>
      {label}
    </button>
  )
}

function pinOf(s: SitePin): MapPin {
  return {
    id: s.id,
    city: s.city,
    lat: s.lat,
    lon: s.lon,
    colour: STATUS[s.status].colour,
    attention: s.attention,
    ariaLabel: `${s.name}, ${s.city} ${s.state}: ${STATUS[s.status].label}. Equipment: ${s.equipment.join(', ') || 'none'}. Phantoms: ${s.phantoms}`,
    lines: [
      { text: s.equipment.join(' · ') || 'No equipment' },
      { text: s.phantoms ? `${s.phantoms} phantom${s.phantoms > 1 ? 's' : ''}` : 'No phantom', className: s.phantoms ? 'sv-phantoms' : 'sv-phantoms none' },
    ],
  }
}

function Fact({ k, v }: { k: string; v: string }) {
  return (
    <div style={{ background: '#F6F8FB', borderRadius: 8, padding: '8px 12px', display: 'flex', flexDirection: 'column', gap: 2 }}>
      <span style={{ fontSize: 11, color: '#5B6B82', textTransform: 'uppercase', letterSpacing: '0.04em' }}>{k}</span>
      <span style={{ fontSize: 14, fontWeight: 600 }}>{v}</span>
    </div>
  )
}

function Line({ k, v }: { k: string; v: string }) {
  return (
    <Flex justify="space-between" gap={16} style={{ padding: '6px 0', borderBottom: '1px solid #EDF0F5', fontSize: 13 }}>
      <span style={{ color: '#5B6B82' }}>{k}</span>
      <span style={{ fontWeight: 600, textAlign: 'right' }}>{v}</span>
    </Flex>
  )
}

function SiteGrid({ site }: { site: SiteDetail }) {
  const kinds = [...site.equipment.map((e) => e.kind), ...site.missing_equipment]
  const order = ['PET/CT', 'SPECT/CT', 'Dose calibrator', 'Gamma counter'].filter((k) => kinds.includes(k as never))
  return (
    <div role="table" aria-label="Isotope validation" className="sv-grid" style={{ gridTemplateColumns: `1.5fr repeat(${site.isotopes.length}, 1fr)` }}>
      <div role="row" style={{ display: 'contents' }}>
        <span role="columnheader" />
        {site.isotopes.map((i) => (
          <span role="columnheader" key={i} className="sv-grid-head">
            {i}
          </span>
        ))}
      </div>
      <div role="row" style={{ display: 'contents' }}>
        <span role="rowheader" className="sv-grid-row">
          Licensed for
        </span>
        {site.isotopes.map((i) => {
          const yes = site.licensed.includes(i)
          return (
            <span role="cell" key={i} className="sv-cell" title={`${i}: ${yes ? 'licensed' : 'not licensed'}`} style={yes ? { background: '#EEF4FF', color: '#0B4FB3' } : { color: '#A9B4D0' }}>
              {yes ? 'Yes' : '–'}
            </span>
          )
        })}
      </div>
      {order.map((kind) => (
        <div role="row" key={kind} style={{ display: 'contents' }}>
          <span role="rowheader" className="sv-grid-row">
            {kind}
          </span>
          {site.grid
            .filter((c) => c.equipment === kind)
            .map((c) => {
              const style: CSSProperties =
                c.state === null
                  ? { background: '#EEF0F4' }
                  : !c.validated && c.state === 'none'
                    ? { border: '1px dashed #D0D7E2', color: '#A9B4D0' }
                    : { background: STATUS[c.state].bg, color: STATUS[c.state].fg }
              return (
                <Tooltip key={c.isotope} title={c.tip}>
                  <span role="cell" className="sv-cell" aria-label={c.tip} style={style}>
                    {c.state === null ? '' : STATUS[c.state].symbol}
                  </span>
                </Tooltip>
              )
            })}
        </div>
      ))}
    </div>
  )
}

function SitePanel({ siteId, onClose }: { siteId?: string; onClose: () => void }) {
  const { data: site, isLoading, isError, error } = useSiteDetail(siteId)
  return (
    <Drawer open={Boolean(siteId)} onClose={onClose} title={site?.name ?? 'Site'} size={560} destroyOnHidden>
      {isError && <Alert type="error" showIcon title="Could not load the site" description={error.message} />}
      {(isLoading || !site) && !isError && <Skeleton active />}
      {site && (
        <Flex vertical gap={14} data-testid="site-panel">
          <Flex justify="space-between" align="center" gap={8} wrap>
            <Typography.Text type="secondary">
              {site.city}, {site.state}
              {site.department ? ` · ${site.department}` : ''}
            </Typography.Text>
            <StatusTag status={site.status} />
          </Flex>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            <Fact k="Site physicist" v={site.physicist ?? 'Not recorded'} />
            <Fact k="ARTnet accreditation" v={site.artnet_accreditation ?? 'Not recorded'} />
            <Fact k="Radiopharmacy / hot lab" v={site.radiopharmacy === null ? 'Not recorded' : site.radiopharmacy ? 'Yes' : 'No'} />
            <Fact k="Last survey" v={formatDay(site.last_survey)} />
          </div>

          <Typography.Title level={5} style={{ margin: '4px 0 0' }}>
            Isotope validation
          </Typography.Title>
          <SiteGrid site={site} />
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            ✓ in date · ! due within 60 days or files missing · ✕ overdue · ○ phantom scan booked · – not validated · grey: not on
            site. Hover a cell for dates.
          </Typography.Text>

          <Typography.Title level={5} style={{ margin: '4px 0 0' }}>
            Equipment on site
          </Typography.Title>
          {site.equipment.map((e) => (
            <details key={e.kind} className="sv-equipment">
              <summary>
                <strong>{e.kind}</strong>
                <span>{[e.manufacturer, e.model].filter(Boolean).join(' · ') || 'Details not recorded'}</span>
              </summary>
              <Line k="Installed" v={formatDay(e.installed)} />
              <Line k="Last calibration" v={formatDay(e.last_calibration)} />
              <Line k="Maintenance / QC schedule" v={e.maintenance ?? '—'} />
              <Line k="Plans to replace" v={e.replacement ?? 'None recorded'} />
            </details>
          ))}
          {site.missing_equipment.length > 0 && (
            <Typography.Text type="secondary" style={{ fontSize: 13 }}>
              Not on site: {site.missing_equipment.join(', ')}
            </Typography.Text>
          )}

          <Typography.Title level={5} style={{ margin: '4px 0 0' }}>
            Phantoms and QA/QC
          </Typography.Title>
          <Flex gap={6} wrap>
            {site.qa.phantoms.length ? (
              site.qa.phantoms.map((p) => (
                <Tag key={p} color="blue">
                  {p}
                </Tag>
              ))
            ) : (
              <Tag>No phantom on site</Tag>
            )}
          </Flex>
          <div>
            <Line k="Used for study-specific scans?" v={site.qa.used_for_study_scans ?? '—'} />
            <Line k="Access to QA/QC records?" v={site.qa.records_access ?? '—'} />
            <Line k="Can submit QA/QC monthly?" v={site.qa.monthly_submission ?? '—'} />
            <Line k="Daily QC data stored" v={site.qa.daily_qc_storage ?? '—'} />
            {Object.entries(site.qa.routines).map(([k, v]) => (
              <Line key={k} k={`QA/QC routine · ${k}`} v={v} />
            ))}
          </div>

          <Typography.Title level={5} style={{ margin: '4px 0 0' }}>
            Phantom scans
          </Typography.Title>
          {site.scans.length === 0 ? (
            <Typography.Text type="secondary">No phantom scans recorded.</Typography.Text>
          ) : (
            site.scans.map((s, i) => (
              <Flex key={i} justify="space-between" gap={12} style={{ padding: '6px 0', borderBottom: '1px solid #EDF0F5', fontSize: 13 }}>
                <span>
                  {s.equipment} {s.isotope} · {s.study} · {formatDay(s.on)}
                </span>
                <Tag style={{ background: SCAN[s.status].bg, color: SCAN[s.status].fg, border: 0, fontWeight: 600 }}>{s.status}</Tag>
              </Flex>
            ))
          )}

          <Typography.Title level={5} style={{ margin: '4px 0 0' }}>
            Image transfer
          </Typography.Title>
          <div>
            <Line k="PACS" v={site.transfer.pacs ?? '—'} />
            <Line k="Exports DICOM?" v={site.transfer.dicom_export ?? '—'} />
            <Line k="Transfer to core lab" v={site.transfer.methods.join(', ') || '—'} />
          </div>

          {site.source_url ? (
            <Button type="primary" href={site.source_url} target="_blank" rel="noreferrer">
              Open in SharePoint
            </Button>
          ) : (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              Demo site. Once connected, changes are made in SharePoint; Avi.Intelligence only reads them.
            </Typography.Text>
          )}
        </Flex>
      )}
    </Drawer>
  )
}

function Lists({ data, open }: { data: SiteValidationReport; open: (id: string) => void }) {
  return (
    <Flex gap={16} wrap align="stretch">
      <Card title="Next physicist reviews" style={{ flex: '1 1 380px', minWidth: 0 }} extra={<RuleInfo rule={data.rules.review ?? ''} />}>
        {data.reviews.length === 0 ? (
          <Typography.Text type="secondary">No reviews due in the next 120 days.</Typography.Text>
        ) : (
          data.reviews.slice(0, 6).map((r) => (
            <button type="button" key={`${r.site_id}-${r.equipment}-${r.isotope}`} className="sv-list-item" onClick={() => open(r.site_id)}>
              <span className="sv-date">
                <small>{new Date(r.next_review).toLocaleString('en-AU', { month: 'short' })}</small>
                <strong>{Number(r.next_review.slice(8, 10))}</strong>
              </span>
              <span style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
                <strong>
                  {r.site} · {r.city}
                </strong>
                <small style={{ color: '#5B6B82' }}>
                  {r.equipment} · {r.isotope}
                  {r.physicist ? ` · ${r.physicist}` : ''}
                </small>
                <small style={{ fontWeight: 600, color: r.days < 0 ? STATUS.overdue.fg : r.days <= 60 ? STATUS.due_soon.fg : '#3D4757' }}>
                  {r.days < 0 ? `Overdue by ${-r.days} days` : `In ${r.days} days`}
                </small>
              </span>
            </button>
          ))
        )}
      </Card>
      <Card title="Phantom scans in progress" style={{ flex: '1 1 380px', minWidth: 0 }}>
        {data.scans.length === 0 ? (
          <Typography.Text type="secondary">No phantom scans in progress.</Typography.Text>
        ) : (
          data.scans.map((s, i) => (
            <button type="button" key={i} className="sv-list-item" onClick={() => open(s.site_id)} style={{ justifyContent: 'space-between' }}>
              <span style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
                <strong>
                  {s.site} · {s.city}
                </strong>
                <small style={{ color: '#5B6B82' }}>
                  {s.equipment} · {s.isotope} · {s.study} · {formatDay(s.on)}
                </small>
              </span>
              <Tag style={{ background: SCAN[s.status].bg, color: SCAN[s.status].fg, border: 0, fontWeight: 600 }}>{s.status}</Tag>
            </button>
          ))
        )}
        <Typography.Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 8 }}>
          Booked → Scanned → Submitted to core lab → Passed or Failed.
        </Typography.Text>
      </Card>
    </Flex>
  )
}

/** Site validation status: equipment, isotope validations and phantoms per site, on a map of Australia. */
export function SiteValidationPage() {
  const { message } = App.useApp()
  const [params, setParams] = useSearchParams()
  const equipment = params.get('equipment') ?? undefined
  const isotope = params.get('isotope') ?? undefined
  const picked = params.get('site') ?? undefined
  const { data, isLoading, isError, error, refetch } = useSiteValidation({ equipment, isotope })
  const refresh = useRefreshSiteValidation()

  const set = (changes: Record<string, string | undefined>) => {
    const next = new URLSearchParams(params)
    for (const [k, v] of Object.entries(changes)) {
      if (v) next.set(k, v)
      else next.delete(k)
    }
    setParams(next, { replace: true })
  }
  const open = (id: string) => set({ site: id })

  if (isError) {
    return (
      <Alert
        type="error"
        showIcon
        title="Could not load site validation"
        description={error.message}
        action={<Button onClick={() => void refetch()}>Try again</Button>}
      />
    )
  }
  if (isLoading || !data) return <Skeleton active paragraph={{ rows: 12 }} />

  const worst = data.tiles.find((t) => t.key === 'overdue')?.value !== '0' ? STATUS.overdue.colour : STATUS.in_date.colour
  const legend: ValidationStatus[] = ['in_date', 'due_soon', 'overdue', 'files_missing', 'booked', 'none']

  return (
    <Flex vertical gap={16}>
      <PageHeader
        title="Site validation status"
        subtitle="What each site has, what is validated for which isotope, and its phantoms. Click a site on the map."
        extra={
          <Flex gap={8} wrap align="center" className="no-print">
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {data.source.mode === 'sharepoint'
                ? `SharePoint · ${data.source.fetched_at ? formatDateTime(data.source.fetched_at) : 'not read yet'}`
                : 'Demo data'}
            </Typography.Text>
            <RuleInfo rule={data.rules.status ?? ''} />
            <Button
              icon={<SyncOutlined />}
              loading={refresh.isPending}
              onClick={() =>
                refresh.mutate(undefined, {
                  onSuccess: () => void message.success('Site validation synced'),
                  onError: (e) => void message.error(e.message),
                })
              }
            >
              Sync now
            </Button>
            <Button icon={<FileExcelOutlined />} href={siteValidationExportUrl({ equipment, isotope })}>
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
          title="Demo sites: the site validation tracker is not connected yet"
          description={`${data.source.reason ?? ''} These sites and results are made up.`}
        />
      )}

      <div data-testid="site-headline" style={{ fontSize: 17, fontWeight: 600, lineHeight: 1.45, background: '#FFFFFF', border: '1px solid #DDE3EC', borderLeft: `5px solid ${worst}`, borderRadius: 10, padding: '14px 18px' }}>
        {data.headline}
      </div>

      <Flex gap={18} wrap align="center" className="no-print" role="group" aria-label="Filters">
        <Flex gap={6} wrap align="center">
          <Typography.Text type="secondary">Equipment</Typography.Text>
          <Chip on={!equipment} label="All" onClick={() => set({ equipment: undefined })} />
          {data.equipment_options.map((e) => (
            <Chip key={e} on={equipment === e} label={e} onClick={() => set({ equipment: e })} />
          ))}
        </Flex>
        <Flex gap={6} wrap align="center">
          <Typography.Text type="secondary">Isotope</Typography.Text>
          <Chip on={!isotope} label="All" onClick={() => set({ isotope: undefined })} />
          {data.isotope_options.map((i) => (
            <Chip key={i} on={isotope === i} label={i} onClick={() => set({ isotope: i })} />
          ))}
        </Flex>
      </Flex>

      <ReportTiles tiles={data.tiles} />

      <section aria-label="Map of sites" style={{ background: '#0B1424', borderRadius: 16, padding: '18px 22px', display: 'flex', flexDirection: 'column', gap: 10 }}>
        <Flex justify="space-between" align="baseline" gap={8} wrap>
          <Typography.Title level={5} style={{ margin: 0, color: '#FFFFFF' }}>
            Sites in Australia
          </Typography.Title>
          <Flex gap={14} wrap style={{ fontSize: 12, color: '#C9D3E3' }}>
            {legend.map((k) => (
              <span key={k} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span aria-hidden="true" style={{ width: 10, height: 10, borderRadius: '50%', background: '#FFFFFF', boxShadow: `0 0 0 3px ${STATUS[k].colour}, 0 0 8px 2px ${STATUS[k].colour}` }} />
                {STATUS[k].label}
              </span>
            ))}
          </Flex>
        </Flex>
        <AustraliaMap pins={data.sites.map(pinOf)} onSelect={open} selected={picked} />
        <Typography.Text style={{ fontSize: 12, color: '#8B9AB3' }}>
          Pulsing: needs attention (overdue, files missing or due soon). Under each city: equipment on site (PET = PET/CT, SPECT =
          SPECT/CT, DC = dose calibrator, GC = gamma counter) and how many phantoms it has.
        </Typography.Text>
      </section>

      <Lists data={data} open={open} />

      <MoreDetail summary={`All validations (${data.rows.length})`}>
        <Table<ValidationRow>
          size="small"
          rowKey={(r) => `${r.site_id}-${r.equipment}-${r.isotope}`}
          dataSource={data.rows}
          pagination={false}
          scroll={{ x: 860 }}
          onRow={(r) => ({ onClick: () => open(r.site_id), style: { cursor: 'pointer' } })}
          columns={[
            { title: 'Site', key: 'site', render: (_, r) => <span><strong>{r.site}</strong> <Typography.Text type="secondary">{r.city} {r.state}</Typography.Text></span> },
            { title: 'Equipment', dataIndex: 'equipment', width: 130 },
            { title: 'Isotope', dataIndex: 'isotope', width: 80 },
            { title: 'Validated by', key: 'by', width: 110, render: (_, r) => r.validated_by ?? '—' },
            { title: 'Validated on', key: 'on', width: 120, render: (_, r) => formatDay(r.validated_on) },
            { title: 'Files', key: 'files', width: 80, render: (_, r) => (r.files_available === null ? '—' : r.files_available ? 'On file' : 'Missing') },
            { title: 'Next review', key: 'next', width: 140, render: (_, r) => (r.next_review ? formatDay(r.next_review) : r.scan_on ? `Scan ${formatDay(r.scan_on)}` : '—') },
            { title: 'Status', key: 'status', width: 130, render: (_, r) => <StatusTag status={r.status} /> },
          ]}
        />
      </MoreDetail>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        {data.rules.source} {data.rules.review}
      </Typography.Text>

      <SitePanel siteId={picked} onClose={() => set({ site: undefined })} />
    </Flex>
  )
}
