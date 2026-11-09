import { Empty, Tabs } from 'antd'
import { useSearchParams } from 'react-router'

import type { ReportFilters, TaskCategory } from '../../api/types'
import { PageHeader } from '../../components/PageHeader'
import { StudyDeliveryTab } from './StudyDeliveryTab'
import { WorkManagementTab } from './WorkManagementTab'

const TABS = [
  { key: 'study', label: 'Study delivery' },
  { key: 'work', label: 'Work management' },
  { key: 'quality', label: 'Quality (SOPs)' },
  { key: 'etmf', label: 'eTMF' },
] as const
type TabKey = (typeof TABS)[number]['key']

const CATEGORIES: TaskCategory[] = ['study', 'sop', 'vendor', 'system', 'general']

const COMING: Record<Exclude<TabKey, 'study' | 'work'>, string> = {
  quality: 'SOP review schedule, library health and the change log are being built next.',
  etmf: 'eTMF completeness, QC pipeline, filing timeliness and expiring documents follow after Quality.',
}

export function ReportsPage() {
  const [params, setParams] = useSearchParams()
  const raw = params.get('tab')
  const tab: TabKey = TABS.some((t) => t.key === raw) ? (raw as TabKey) : 'study'
  const filters: ReportFilters = {
    study_id: params.get('study') ?? undefined,
    site_id: params.get('site') ?? undefined,
  }

  const update = (changes: Record<string, string | undefined>) => {
    const next = new URLSearchParams(params)
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value)
      else next.delete(key)
    }
    setParams(next, { replace: true })
  }

  return (
    <>
      <PageHeader
        title="Reports and Insights"
        subtitle="How studies, work, SOPs and the eTMF are tracking. Hover a chart for exact numbers."
      />
      <Tabs
        className="no-print"
        activeKey={tab}
        onChange={(key) => update({ tab: key === 'study' ? undefined : key })}
        items={TABS.map((t) => ({ key: t.key, label: t.label }))}
      />
      {tab === 'study' ? (
        <StudyDeliveryTab
          filters={filters}
          onFilters={(f) => update({ study: f.study_id, site: f.site_id })}
        />
      ) : tab === 'work' ? (
        <WorkManagementTab
          filters={{ study_id: filters.study_id, category: CATEGORIES.find((c) => c === params.get('category')) }}
          onFilters={(f) => update({ study: f.study_id, category: f.category })}
        />
      ) : (
        <Empty description={COMING[tab]} style={{ padding: '48px 0' }} />
      )}
    </>
  )
}
