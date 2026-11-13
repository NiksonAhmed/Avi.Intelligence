import { Tabs } from 'antd'
import { useSearchParams } from 'react-router'

import type { ReportFilters, TaskCategory } from '../../api/types'
import { PageHeader } from '../../components/PageHeader'
import { CHANGE_PERIODS } from '../../lib/reports'
import { DeviationsTab } from './DeviationsTab'
import { EtmfTab } from './EtmfTab'
import { RisksIssuesTab } from './RisksIssuesTab'
import { QualityTab } from './QualityTab'
import { StudyDeliveryTab } from './StudyDeliveryTab'
import { WorkManagementTab } from './WorkManagementTab'

const TABS = [
  { key: 'study', label: 'Study delivery' },
  { key: 'work', label: 'Work management' },
  { key: 'quality', label: 'Quality (SOPs)' },
  { key: 'etmf', label: 'eTMF' },
  { key: 'deviations', label: 'Protocol deviations' },
  { key: 'risks', label: 'Risks and issues' },
] as const
type TabKey = (typeof TABS)[number]['key']

const CATEGORIES: TaskCategory[] = ['study', 'sop', 'vendor', 'system', 'general']

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
        subtitle="How studies, work, SOPs, the eTMF, protocol deviations and risks and issues are tracking. Hover a chart for exact numbers."
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
      ) : tab === 'quality' ? (
        <QualityTab
          filters={{
            department: params.get('department') ?? undefined,
            months: CHANGE_PERIODS.find((m) => String(m) === params.get('months')),
          }}
          onFilters={(f) => update({ department: f.department, months: f.months ? String(f.months) : undefined })}
        />
      ) : tab === 'risks' ? (
        <RisksIssuesTab filters={filters} onFilters={(f) => update({ study: f.study_id, site: f.site_id })} />
      ) : tab === 'deviations' ? (
        <DeviationsTab filters={filters} onFilters={(f) => update({ study: f.study_id, site: f.site_id })} />
      ) : (
        <EtmfTab filters={filters} onFilters={(f) => update({ study: f.study_id, site: f.site_id })} />
      )}
    </>
  )
}
