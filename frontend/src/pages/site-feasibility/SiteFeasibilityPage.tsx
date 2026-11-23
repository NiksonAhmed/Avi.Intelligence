import { FileExcelOutlined, FilePdfOutlined, SyncOutlined } from '@ant-design/icons'
import { Alert, App, Button, Card, Drawer, Flex, Progress, Select, Skeleton, Table, Tabs, Tag, Typography } from 'antd'
import type { ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router'

import { siteFeasibilityExportUrl } from '../../api/client'
import { useFeasibilityDetail, useRefreshSiteFeasibility, useSiteFeasibility } from '../../api/hooks'
import type { FeasibilityPin, FeasibilityRow, Recommendation, SiteFeasibilityDetail } from '../../api/types'
import { PageHeader } from '../../components/PageHeader'
import { formatDateTime, formatDay } from '../../lib/format'
import { MoreDetail, ReportTiles, RuleInfo } from '../reports/ReportParts'
import { AustraliaMap } from '../site-validation/SiteMap'
import type { MapPin } from '../site-validation/SiteMap'

const REC: Record<Recommendation, { label: string; colour: string; bg: string; fg: string }> = {
  both: { label: 'Diagnostics and therapeutics', colour: '#2EE6A0', bg: '#DCF5E7', fg: '#14633A' },
  therapeutics: { label: 'Therapeutics only', colour: '#38BDF8', bg: '#E0F2FE', fg: '#075985' },
  diagnostics: { label: 'Diagnostics only', colour: '#F472B6', bg: '#FCE7F3', fg: '#9D174D' },
  not_recommended: { label: 'Not recommended', colour: '#FF5C5C', bg: '#FDE8E6', fg: '#A1210F' },
  not_assessed: { label: 'Not assessed', colour: '#A9B4D0', bg: '#EEF0F4', fg: '#3D4757' },
}
const ISOTOPE_ROWS: { key: 'licensed' | 'trained' | 'handled'; label: string }[] = [
  { key: 'licensed', label: 'Licensed for' },
  { key: 'trained', label: 'Staff trained' },
  { key: 'handled', label: 'Handled before' },
]
const weeks = (v: number | null) => (v === null ? null : `${v} weeks`)

function RecTag({ rec }: { rec: Recommendation }) {
  const r = REC[rec]
  return <Tag style={{ background: r.bg, color: r.fg, border: 0, fontWeight: 600 }}>{r.label}</Tag>
}

function Chip({ on, label, onClick }: { on: boolean; label: string; onClick: () => void }) {
  return (
    <button type="button" aria-pressed={on} onClick={onClick} className={`sv-chip${on ? ' on' : ''}`}>
      {label}
    </button>
  )
}

function NotAnswered() {
  return (
    <Typography.Text type="secondary" italic style={{ fontWeight: 400 }}>
      Not answered
    </Typography.Text>
  )
}

/** One question and its answer; an empty answer shows as "Not answered". */
function Line({ k, v }: { k: string; v: ReactNode }) {
  const empty = v === null || v === undefined || v === ''
  return (
    <Flex justify="space-between" gap={16} style={{ padding: '6px 0', borderBottom: '1px solid #EDF0F5', fontSize: 13 }}>
      <span style={{ color: '#5B6B82' }}>{k}</span>
      <span style={{ fontWeight: 600, textAlign: 'right' }}>{empty ? <NotAnswered /> : v}</span>
    </Flex>
  )
}

function Fact({ k, v }: { k: string; v: ReactNode }) {
  return (
    <div style={{ background: '#F6F8FB', borderRadius: 8, padding: '8px 12px', display: 'flex', flexDirection: 'column', gap: 2 }}>
      <span style={{ fontSize: 11, color: '#5B6B82', textTransform: 'uppercase', letterSpacing: '0.04em' }}>{k}</span>
      <span style={{ fontSize: 14, fontWeight: 600 }}>{v ?? <NotAnswered />}</span>
    </div>
  )
}

function YesNo({ v }: { v: string | null }) {
  if (v === null) return <NotAnswered />
  const colour = v === 'Yes' ? 'green' : v === 'No' ? 'default' : 'gold'
  return <Tag color={colour}>{v}</Tag>
}

function pinOf(s: FeasibilityPin): MapPin {
  const rec = REC[s.recommendation]
  return {
    id: s.id,
    city: s.city,
    lat: s.lat,
    lon: s.lon,
    colour: rec.colour,
    attention: s.survey_due,
    ariaLabel: `${s.name}, ${s.city} ${s.state}: ${rec.label}. Accepting new trials: ${s.accepting ?? 'not answered'}.${s.survey_due ? ' Survey due.' : ''}`,
    lines: [
      { text: s.short },
      s.accepting === 'No'
        ? { text: 'Not accepting trials', className: 'sv-phantoms none' }
        : { text: s.hrec_weeks === null ? 'HREC: not answered' : `HREC ${s.hrec_weeks} wk`, className: 'sv-phantoms' },
    ],
  }
}

function IsotopeGrid({ site }: { site: SiteFeasibilityDetail }) {
  const isotopes = ['64Cu', '68Ga', '90Y', '177Lu', '225Ac']
  return (
    <div role="table" aria-label="IP readiness by isotope" className="sv-grid" style={{ gridTemplateColumns: `1.5fr repeat(${isotopes.length}, 1fr)` }}>
      <div role="row" style={{ display: 'contents' }}>
        <span role="columnheader" />
        {isotopes.map((i) => (
          <span role="columnheader" key={i} className="sv-grid-head">
            {i}
          </span>
        ))}
      </div>
      {ISOTOPE_ROWS.map((row) => (
        <div role="row" key={row.key} style={{ display: 'contents' }}>
          <span role="rowheader" className="sv-grid-row">
            {row.label}
          </span>
          {isotopes.map((i) => {
            const yes = site.ip[row.key].includes(i)
            return (
              <span role="cell" key={i} className="sv-cell" title={`${row.label} ${i}: ${yes ? 'yes' : 'no'}`} style={yes ? { background: '#DCF5E7', color: '#14633A' } : { color: '#A9B4D0' }}>
                {yes ? '✓' : '–'}
              </span>
            )
          })}
        </div>
      ))}
    </div>
  )
}

function SitePanel({ siteId, onClose }: { siteId?: string; onClose: () => void }) {
  const { data: site, isLoading, isError, error } = useFeasibilityDetail(siteId)
  return (
    <Drawer open={Boolean(siteId)} onClose={onClose} title={site?.name ?? 'Site'} size={600} destroyOnHidden>
      {isError && <Alert type="error" showIcon title="Could not load the site" description={error.message} />}
      {(isLoading || !site) && !isError && <Skeleton active />}
      {site && (
        <Flex vertical gap={14} data-testid="feasibility-panel">
          <Flex justify="space-between" align="center" gap={8} wrap>
            <Typography.Text type="secondary">
              {[`${site.city}, ${site.state}`, site.department, site.sector].filter(Boolean).join(' · ')}
            </Typography.Text>
            <Flex gap={4} wrap>
              <RecTag rec={site.recommendation} />
              {site.survey_due && <Tag color="gold">Survey due</Tag>}
            </Flex>
          </Flex>
          {site.withdrawal && <Alert type="warning" showIcon title="Known PI or site withdrawal" description={site.withdrawal} />}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            <Fact k="Accepting new trials" v={site.accepting} />
            <Fact k="Last survey" v={site.last_survey ? `${formatDay(site.last_survey)}${site.last_survey_study ? ` · ${site.last_survey_study}` : ''}` : null} />
            <Fact k="Survey answered" v={<Progress percent={site.answered} size="small" style={{ margin: 0 }} />} />
            <Fact k="Performance score" v={site.score === null ? 'No study run yet' : `${site.score} of ${site.score_max}`} />
          </div>
          {site.validation_site_id && (
            <Link to={`/site-validation?site=${encodeURIComponent(site.validation_site_id)}`}>
              <Button block>Open on Site validation: equipment, isotope validations and phantoms</Button>
            </Link>
          )}

          <Tabs
            size="small"
            items={[
              {
                key: 'readiness',
                label: 'Start-up',
                children: (
                  <div>
                    <Line k="Start-up (predicted)" v={weeks(site.timelines.startup_weeks)} />
                    <Line k="SIV (predicted)" v={weeks(site.timelines.siv_weeks)} />
                    <Line k="FPI (predicted)" v={weeks(site.timelines.fpi_weeks)} />
                    <Line k="HREC turnaround" v={weeks(site.admin.hrec_weeks)} />
                    <Line k="Central or private HREC?" v={site.admin.central_hrec} />
                    <Line k="Additional approvals" v={site.admin.additional_approvals} />
                    <Line k="Contract and budget during HREC review?" v={site.admin.contract_during_hrec} />
                    <Line k="Contract and budget to final" v={weeks(site.admin.contract_weeks)} />
                  </div>
                ),
              },
              {
                key: 'ip',
                label: 'IP',
                children: (
                  <Flex vertical gap={10}>
                    <IsotopeGrid site={site} />
                    <div>
                      <Line k="Treatment days and times" v={site.ip.treatment_days} />
                      <Line k="Radioactive fridges (4 °C)" v={site.ip.fridges} />
                      <Line k="Radioactive −20 °C freezers" v={site.ip.freezers_20} />
                      <Line k="Radioactive −80 °C freezers" v={site.ip.freezers_80} />
                    </div>
                  </Flex>
                ),
              },
              {
                key: 'equipment',
                label: 'Equipment',
                children: (
                  <div data-testid="feasibility-equipment">
                    {Object.entries(site.equipment).map(([k, v]) => (
                      <Line key={k} k={k} v={<YesNo v={v} />} />
                    ))}
                    <Typography.Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 8 }}>
                      Scanners, dose calibrators and gamma counters in detail: see Site validation.
                    </Typography.Text>
                  </div>
                ),
              },
              {
                key: 'admin',
                label: 'Administrative',
                children: (
                  <div>
                    <Line k="Clinical trial audit?" v={site.admin.audited} />
                    <Line k="Auditor" v={site.admin.auditor} />
                    <Line k="Major findings?" v={site.admin.major_findings} />
                    <Line k="SOPs for clinical trials?" v={site.admin.sops} />
                    <Line k="Radiation safety licence" v={site.admin.radiation_licence} />
                    <Line k="ARTnet accreditation" v={site.admin.artnet} />
                    <Line k="Remote monitoring?" v={site.admin.remote_monitoring} />
                    <Line k="Records accessible remotely" v={site.admin.remote_records} />
                  </div>
                ),
              },
              {
                key: 'experience',
                label: 'Experience',
                children: (
                  <Flex vertical gap={10}>
                    <div>
                      <Line k="Imaging trials?" v={site.experience.imaging_trials} />
                      <Line k="Therapeutic trials?" v={site.experience.therapeutic_trials} />
                      <Line k="Radioisotopes" v={site.experience.isotopes.join(', ') || null} />
                      <Line k="Finding eligible patients" v={site.experience.patient_identification} />
                      <Line k="Imaging trials actively enrolling" v={site.experience.active_imaging_trials} />
                    </div>
                    <Table
                      size="small"
                      rowKey="indication"
                      pagination={false}
                      dataSource={site.experience.by_indication}
                      onRow={() => ({ 'data-testid': 'experience-row' }) as never}
                      columns={[
                        { title: 'Indication', dataIndex: 'indication' },
                        { title: 'Experience', key: 'e', width: 100, render: (_, r) => <YesNo v={r.experience} /> },
                        { title: 'Imaging trials', key: 'i', width: 100, align: 'right', render: (_, r) => r.imaging ?? '—' },
                        { title: 'Therapeutic trials', key: 't', width: 110, align: 'right', render: (_, r) => r.therapeutic ?? '—' },
                      ]}
                    />
                  </Flex>
                ),
              },
              {
                key: 'performance',
                label: 'Performance',
                children: site.performance ? (
                  <Flex vertical gap={12} data-testid="feasibility-performance">
                    {site.performance.projects.map((p) => (
                      <Card key={p.protocol} size="small" title={`${p.protocol}${p.indication ? ` · ${p.indication}` : ''}`}>
                        <Line k="Expected enrolment" v={p.expected_min !== null ? `${p.expected_min} to ${p.expected_max ?? '?'}` : null} />
                        <Line k="Actual enrolment" v={p.actual} />
                      </Card>
                    ))}
                    <Typography.Text strong>
                      Overall site assessment: {site.score} of {site.score_max}
                    </Typography.Text>
                    {site.score_rows.map((r) => (
                      <Flex key={r.criterion} align="center" gap={10} style={{ fontSize: 13 }}>
                        <span style={{ width: 170, flexShrink: 0, color: '#3D4757' }}>{r.criterion}</span>
                        <Progress
                          percent={r.score === null ? 0 : (100 * r.score) / r.max}
                          showInfo={false}
                          size="small"
                          style={{ flex: 1, margin: 0 }}
                          strokeColor={r.score !== null && r.score / r.max < 0.5 ? '#E5484D' : '#1677FF'}
                        />
                        <span style={{ width: 44, textAlign: 'right', fontWeight: 600 }}>{r.score === null ? '—' : `${r.score}/${r.max}`}</span>
                      </Flex>
                    ))}
                    <Line k="Directly competing trials?" v={site.performance.competing_trials} />
                  </Flex>
                ) : (
                  <Typography.Text type="secondary">No study has run at this site yet: the assessment is filled in after activation.</Typography.Text>
                ),
              },
            ]}
          />

          {site.source_url ? (
            <Button type="primary" href={site.source_url} target="_blank" rel="noreferrer">
              Open in SharePoint
            </Button>
          ) : (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              Demo site. Once connected, answers are kept in SharePoint; Avi.Intelligence only reads them.
            </Typography.Text>
          )}
        </Flex>
      )}
    </Drawer>
  )
}

/** Site feasibility: can a site run our studies? Recommendation, IP, equipment, start-up and experience. */
export function SiteFeasibilityPage() {
  const { message } = App.useApp()
  const [params, setParams] = useSearchParams()
  const isotope = params.get('isotope') ?? undefined
  const indication = params.get('indication') ?? undefined
  const recommendation = params.get('recommendation') ?? undefined
  const picked = params.get('site') ?? undefined
  const { data, isLoading, isError, error, refetch } = useSiteFeasibility({ isotope, indication, recommendation })
  const refresh = useRefreshSiteFeasibility()

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
        title="Could not load site feasibility"
        description={error.message}
        action={<Button onClick={() => void refetch()}>Try again</Button>}
      />
    )
  }
  if (isLoading || !data) return <Skeleton active paragraph={{ rows: 12 }} />

  const legend: Recommendation[] = ['both', 'therapeutics', 'diagnostics', 'not_recommended', 'not_assessed']

  return (
    <Flex vertical gap={16}>
      <PageHeader
        title="Site feasibility"
        subtitle="Can a site run our studies? Recommendation, IP readiness, equipment, start-up and experience. Click a site on the map."
        extra={
          <Flex gap={8} wrap align="center" className="no-print">
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {data.source.mode === 'sharepoint'
                ? `SharePoint · ${data.source.fetched_at ? formatDateTime(data.source.fetched_at) : 'not read yet'}`
                : 'Demo data'}
            </Typography.Text>
            <RuleInfo rule={[data.rules.recommendation, data.rules.survey, data.rules.answered, data.rules.score].join(' ')} />
            <Button
              icon={<SyncOutlined />}
              loading={refresh.isPending}
              onClick={() =>
                refresh.mutate(undefined, {
                  onSuccess: () => void message.success('Site feasibility synced'),
                  onError: (e) => void message.error(e.message),
                })
              }
            >
              Sync now
            </Button>
            <Button icon={<FileExcelOutlined />} href={siteFeasibilityExportUrl({ isotope, indication, recommendation })}>
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
          title="Demo sites: the site feasibility tracker is not connected yet"
          description={`${data.source.reason ?? ''} These sites and answers are made up.`}
        />
      )}

      <div
        data-testid="feasibility-headline"
        style={{ fontSize: 17, fontWeight: 600, lineHeight: 1.45, background: '#FFFFFF', border: '1px solid #DDE3EC', borderLeft: '5px solid #2EE6A0', borderRadius: 10, padding: '14px 18px' }}
      >
        {data.headline}
      </div>

      <Flex vertical gap={10} className="no-print" role="group" aria-label="Filters">
        <Flex gap={6} wrap align="center">
          <Typography.Text type="secondary">Recommended for</Typography.Text>
          <Chip on={!recommendation} label="All" onClick={() => set({ recommendation: undefined })} />
          {data.recommendation_options.map((r) => (
            <Chip key={r.value} on={recommendation === r.value} label={r.label} onClick={() => set({ recommendation: r.value })} />
          ))}
        </Flex>
        <Flex gap={18} wrap align="center">
          <Flex gap={6} wrap align="center">
            <Typography.Text type="secondary">Licensed for</Typography.Text>
            <Chip on={!isotope} label="All" onClick={() => set({ isotope: undefined })} />
            {data.isotope_options.map((i) => (
              <Chip key={i} on={isotope === i} label={i} onClick={() => set({ isotope: i })} />
            ))}
          </Flex>
          <Flex gap={6} align="center">
            <Typography.Text type="secondary">Experience in</Typography.Text>
            <Select
              aria-label="Filter by indication experience"
              allowClear
              placeholder="Any indication"
              value={indication}
              onChange={(v?: string) => set({ indication: v })}
              options={data.indication_options.map((i) => ({ value: i, label: i }))}
              style={{ width: 280, maxWidth: '100%' }}
              popupMatchSelectWidth={false}
            />
          </Flex>
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
                <span aria-hidden="true" style={{ width: 10, height: 10, borderRadius: '50%', background: '#FFFFFF', boxShadow: `0 0 0 3px ${REC[k].colour}, 0 0 8px 2px ${REC[k].colour}` }} />
                {REC[k].label}
              </span>
            ))}
          </Flex>
        </Flex>
        <AustraliaMap pins={data.sites.map(pinOf)} onSelect={open} selected={picked} />
        <Typography.Text style={{ fontSize: 12, color: '#8B9AB3' }}>
          Colour: what the site is recommended for. Pulsing: survey over 12 months old. Under each city: the recommendation (Diag =
          diagnostics, Ther = therapeutics) and the HREC turnaround.
        </Typography.Text>
      </section>

      <Flex gap={16} wrap align="stretch">
        <Card title="Fastest predicted start-up" style={{ flex: '1 1 380px', minWidth: 0 }} extra={<RuleInfo rule={data.rules.weeks ?? ''} />}>
          {data.fastest.length === 0 ? (
            <Typography.Text type="secondary">No recommended sites with a predicted start-up.</Typography.Text>
          ) : (
            data.fastest.map((f) => (
              <button type="button" key={f.site_id} className="sv-list-item" onClick={() => open(f.site_id)} style={{ justifyContent: 'space-between' }}>
                <span style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
                  <strong>
                    {f.site} · {f.city}
                  </strong>
                  <small style={{ color: '#5B6B82' }}>
                    HREC {f.hrec_weeks ?? '—'} wk · contract {f.contract_weeks ?? '—'} wk
                  </small>
                </span>
                <Tag color="blue" style={{ fontWeight: 600 }}>
                  {f.startup_weeks} wk start-up
                </Tag>
              </button>
            ))
          )}
        </Card>
        <Card title="Surveys due" style={{ flex: '1 1 380px', minWidth: 0 }} extra={<RuleInfo rule={data.rules.survey ?? ''} />}>
          {data.surveys_due.length === 0 ? (
            <Typography.Text type="secondary">Every survey is less than 12 months old.</Typography.Text>
          ) : (
            data.surveys_due.map((d) => (
              <button type="button" key={d.site_id} className="sv-list-item" onClick={() => open(d.site_id)} style={{ justifyContent: 'space-between' }}>
                <span style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
                  <strong>
                    {d.site} · {d.city}
                  </strong>
                  <small style={{ color: '#5B6B82' }}>Last survey {d.last_survey ? formatDay(d.last_survey) : 'never'}</small>
                </span>
                <Tag color="gold" style={{ fontWeight: 600 }}>
                  {d.months === null ? 'Never surveyed' : `${d.months} months ago`}
                </Tag>
              </button>
            ))
          )}
        </Card>
      </Flex>

      <MoreDetail summary={`More detail: all sites (${data.rows.length})`}>
        <Table<FeasibilityRow>
          size="small"
          rowKey="site_id"
          dataSource={data.rows}
          pagination={false}
          scroll={{ x: 1100 }}
          onRow={(r) => ({ onClick: () => open(r.site_id), style: { cursor: 'pointer' }, 'data-testid': 'feasibility-row' }) as never}
          columns={[
            { title: 'Site', key: 'site', render: (_, r) => <span><strong>{r.site}</strong> <Typography.Text type="secondary">{r.city} {r.state}</Typography.Text></span> },
            { title: 'Sector', key: 'sector', width: 80, render: (_, r) => r.sector ?? '—' },
            { title: 'Accepting', key: 'accepting', width: 90, render: (_, r) => r.accepting ?? '—' },
            { title: 'Recommended for', key: 'rec', width: 200, render: (_, r) => <RecTag rec={r.recommendation} /> },
            { title: 'Licensed for', key: 'lic', width: 150, render: (_, r) => r.licensed.join(', ') || '—' },
            { title: 'HREC', key: 'hrec', width: 70, render: (_, r) => (r.hrec_weeks === null ? '—' : `${r.hrec_weeks} wk`) },
            { title: 'Start-up', key: 'start', width: 80, render: (_, r) => (r.startup_weeks === null ? '—' : `${r.startup_weeks} wk`) },
            { title: 'Last survey', key: 'survey', width: 130, render: (_, r) => (<span>{formatDay(r.last_survey)}{r.survey_due && <Tag color="gold" style={{ marginLeft: 6 }}>Due</Tag>}</span>) },
            { title: 'Answered', key: 'answered', width: 90, render: (_, r) => `${r.answered}%` },
            { title: 'Score', key: 'score', width: 70, render: (_, r) => (r.score === null ? '—' : `${r.score}/40`) },
          ]}
        />
      </MoreDetail>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        {data.rules.source} {data.rules.recommendation}
      </Typography.Text>

      <SitePanel siteId={picked} onClose={() => set({ site: undefined })} />
    </Flex>
  )
}
