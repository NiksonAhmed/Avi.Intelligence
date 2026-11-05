import { Alert, Button, Card, Col, Empty, Flex, Input, Progress, Row, Select, Statistic, Table, Tag, Tooltip, Typography } from 'antd'
import type { TableColumnsType } from 'antd'
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router'

import { useStudies } from '../../api/hooks'
import type { StudyFilters, StudySummary } from '../../api/types'
import { PageHeader } from '../../components/PageHeader'
import { StudySourceBanner } from '../../components/StudySourceBanner'
import { ToneTag } from '../../components/ToneTag'
import { formatDay } from '../../lib/format'
import { MILESTONE_STATE, enrolmentText } from '../../lib/studies'

function readFilters(params: URLSearchParams): StudyFilters {
  return {
    q: params.get('q') ?? undefined,
    status: params.get('status') ?? undefined,
    phase: params.get('phase') ?? undefined,
  }
}

export function EnrolmentCell({ study }: { study: Pick<StudySummary, 'enrolled' | 'enrolment_target' | 'enrolment_percent'> }) {
  const text = enrolmentText(study.enrolled, study.enrolment_target, study.enrolment_percent)
  if (study.enrolment_percent === null) {
    return <Typography.Text type="secondary">{text}</Typography.Text>
  }
  return (
    <div style={{ minWidth: 140 }}>
      <Progress
        percent={Math.min(study.enrolment_percent, 100)}
        showInfo={false}
        size="small"
        aria-label={`Enrolment ${text}`}
      />
      <Typography.Text style={{ fontSize: 12 }}>{text}</Typography.Text>
    </div>
  )
}

export function StudyPortfolioPage() {
  const [params, setParams] = useSearchParams()
  const filters = readFilters(params)
  const [searchText, setSearchText] = useState(filters.q ?? '')
  const { data, isLoading, isError, error, refetch } = useStudies(filters)

  const setFilter = (key: keyof StudyFilters, value: string | undefined) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }
  const hasFilters = Boolean(filters.q || filters.status || filters.phase)
  const rules = data?.rules ?? {}

  const columns: TableColumnsType<StudySummary> = [
    {
      title: 'Protocol',
      dataIndex: 'protocol_number',
      width: 140,
      render: (p: string, s) => (
        <Link to={`/command-centre/${s.id}`} style={{ fontWeight: 500, whiteSpace: 'nowrap' }}>
          {p}
        </Link>
      ),
    },
    {
      title: 'Study',
      dataIndex: 'title',
      minWidth: 280,
      render: (title: string, s) => (
        <div>
          <Link to={`/command-centre/${s.id}`}>{title}</Link>
          <div>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {[s.sponsor, s.therapeutic_area].filter(Boolean).join(' · ')}
            </Typography.Text>
          </div>
          {!s.in_source && <Tag color="error">No longer in SimpleTrials</Tag>}
        </div>
      ),
    },
    { title: 'Phase', dataIndex: 'phase', width: 100, render: (v: string | null) => v ?? '—' },
    { title: 'Status', dataIndex: 'status', width: 120, render: (v: string | null) => (v ? <Tag>{v}</Tag> : '—') },
    { title: 'Sites', dataIndex: 'site_count', width: 70, responsive: ['lg'] },
    {
      title: <Tooltip title={rules.enrolment}>Enrolment</Tooltip>,
      key: 'enrolment',
      width: 170,
      responsive: ['md'],
      render: (_: unknown, s) => <EnrolmentCell study={s} />,
    },
    {
      title: 'Next milestone',
      key: 'next',
      width: 200,
      responsive: ['lg'],
      render: (_: unknown, s) =>
        s.next_milestone ? (
          <div>
            <div>{s.next_milestone.name}</div>
            <Flex gap={6} align="center">
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {formatDay(s.next_milestone.planned_date)}
              </Typography.Text>
              <ToneTag
                tone={MILESTONE_STATE[s.next_milestone.state]}
                help={s.next_milestone.state === 'overdue' ? rules.milestone_overdue : undefined}
              />
            </Flex>
          </div>
        ) : (
          <Typography.Text type="secondary">None planned</Typography.Text>
        ),
    },
    {
      title: <Tooltip title={rules.milestone_overdue}>Overdue</Tooltip>,
      dataIndex: 'overdue_milestones',
      width: 90,
      render: (n: number) =>
        n > 0 ? <ToneTag tone={{ ...MILESTONE_STATE.overdue, label: String(n) }} /> : <span>0</span>,
    },
    {
      title: 'Open work',
      key: 'work',
      width: 110,
      responsive: ['xl'],
      render: (_: unknown, s) => (
        <Typography.Text style={{ fontSize: 13 }}>
          {s.open_tasks} {s.open_tasks === 1 ? 'task' : 'tasks'}
          <br />
          {s.open_risks} {s.open_risks === 1 ? 'risk' : 'risks'}
        </Typography.Text>
      ),
    },
  ]

  const all = data?.studies ?? []
  return (
    <>
      <PageHeader title="Study Portfolio" subtitle="All studies, with milestones and enrolment from SimpleTrials." />

      {isError && (
        <Alert
          type="error"
          showIcon
          style={{ marginBottom: 16 }}
          title="Could not load studies"
          description={error.message}
          action={<Button onClick={() => void refetch()}>Try again</Button>}
        />
      )}
      {data && <StudySourceBanner source={data.source} />}

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        {[
          { label: 'Studies', value: data?.total_unfiltered },
          {
            label: 'Overdue milestones',
            value: data ? all.reduce((n, s) => n + s.overdue_milestones, 0) : undefined,
            help: rules.milestone_overdue,
          },
          { label: 'Open tasks', value: data ? all.reduce((n, s) => n + s.open_tasks, 0) : undefined },
          { label: 'Open risks and issues', value: data ? all.reduce((n, s) => n + s.open_risks, 0) : undefined },
        ].map((s) => (
          <Col key={s.label} xs={12} lg={6}>
            <Card size="small" loading={isLoading}>
              <Statistic
                title={s.help ? <Tooltip title={s.help}>{s.label}</Tooltip> : s.label}
                value={s.value ?? '—'}
              />
            </Card>
          </Col>
        ))}
      </Row>

      <Card>
        <Flex gap={12} wrap style={{ marginBottom: 16 }} role="search" aria-label="Filter studies">
          <Input.Search
            aria-label="Search studies"
            placeholder="Search protocol, title, sponsor or PM"
            allowClear
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            onSearch={(v) => setFilter('q', v.trim() || undefined)}
            style={{ width: 320, maxWidth: '100%' }}
          />
          <Select
            aria-label="Filter by study status"
            placeholder="All statuses"
            allowClear
            value={filters.status}
            onChange={(v?: string) => setFilter('status', v)}
            options={(data?.statuses ?? []).map((s) => ({ value: s, label: s }))}
            style={{ width: 170 }}
          />
          <Select
            aria-label="Filter by phase"
            placeholder="All phases"
            allowClear
            value={filters.phase}
            onChange={(v?: string) => setFilter('phase', v)}
            options={(data?.phases ?? []).map((s) => ({ value: s, label: s }))}
            style={{ width: 150 }}
          />
          {hasFilters && (
            <Button
              onClick={() => {
                setSearchText('')
                setParams(new URLSearchParams(), { replace: true })
              }}
            >
              Clear filters
            </Button>
          )}
        </Flex>
        <Table<StudySummary>
          rowKey="id"
          size="middle"
          columns={columns}
          dataSource={all}
          loading={isLoading}
          pagination={{ pageSize: 25, hideOnSinglePage: true, showSizeChanger: false }}
          locale={{
            emptyText: (
              <Empty
                description={
                  data && data.total_unfiltered === 0
                    ? 'No studies have been synced from SimpleTrials yet.'
                    : 'No studies match these filters.'
                }
              />
            ),
          }}
        />
      </Card>
    </>
  )
}
