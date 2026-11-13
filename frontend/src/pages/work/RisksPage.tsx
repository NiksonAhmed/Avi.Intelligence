import { BarChartOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Checkbox, Flex, Select, Typography } from 'antd'
import { Link, useSearchParams } from 'react-router'

import { useRisks, useStudies } from '../../api/hooks'
import { PageHeader } from '../../components/PageHeader'
import { SyncNowButton } from '../../components/SyncNowButton'
import { SimpleTrialsIssues } from '../../components/work/SimpleTrialsIssues'

/** Risks and issues all come from SimpleTrials (the CTMS); nothing is raised or edited here. */
export function RisksPage() {
  const [params, setParams] = useSearchParams()
  const studyId = params.get('study') ?? undefined
  const includeClosed = params.get('closed') === '1'
  const { data, isLoading, isError, error, refetch } = useRisks({ study_id: studyId, include_closed: includeClosed })
  const studies = useStudies()

  const setParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }

  return (
    <>
      <PageHeader
        title="Risks and Issues"
        subtitle="From SimpleTrials, the CTMS, across all studies. Overdue first."
        extra={
          <Flex gap={8} wrap>
            <SyncNowButton kind="simpletrials" />
            <Link to="/reports?tab=risks">
              <Button icon={<BarChartOutlined />}>Dashboard</Button>
            </Link>
          </Flex>
        }
      />
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        title="Risks and issues are managed in SimpleTrials"
        description="Raise and update them in SimpleTrials; changes appear here after the next sync. SimpleTrials' API has no risk register, so its action items are shown as issues."
      />
      {isError && (
        <Alert
          type="error"
          showIcon
          style={{ marginBottom: 16 }}
          title="Could not load risks and issues"
          description={error.message}
          action={<Button onClick={() => void refetch()}>Try again</Button>}
        />
      )}
      <Card>
        <Flex gap={16} wrap align="center" style={{ marginBottom: 16 }}>
          <Select
            aria-label="Filter by study"
            allowClear
            placeholder="All studies"
            value={studyId}
            onChange={(v?: string) => setParam('study', v ?? null)}
            options={(studies.data?.studies ?? []).map((s) => ({ value: s.id, label: `${s.protocol_number} · ${s.title}` }))}
            style={{ width: 300, maxWidth: '100%' }}
            popupMatchSelectWidth={false}
          />
          <Checkbox checked={includeClosed} onChange={(e) => setParam('closed', e.target.checked ? '1' : null)}>
            Show closed
          </Checkbox>
          <Typography.Text type="secondary" style={{ marginLeft: 'auto' }}>
            {data ? `${data.simpletrials_issues.length} shown` : ''}
          </Typography.Text>
        </Flex>
        <SimpleTrialsIssues issues={data?.simpletrials_issues ?? []} loading={isLoading} showStudy />
      </Card>
    </>
  )
}
