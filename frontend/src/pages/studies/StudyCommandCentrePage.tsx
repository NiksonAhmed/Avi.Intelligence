import { PlusOutlined } from '@ant-design/icons'
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Empty,
  Flex,
  Result,
  Row,
  Skeleton,
  Statistic,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'

import { useRisks, useStudies, useStudy, useTasks } from '../../api/hooks'
import type { Milestone, Risk, StudySite, Task } from '../../api/types'
import { ApiError } from '../../api/client'
import { PageHeader } from '../../components/PageHeader'
import { ProvenanceTag } from '../../components/ProvenanceTag'
import { StudySourceBanner } from '../../components/StudySourceBanner'
import { ToneTag } from '../../components/ToneTag'
import { RiskFormModal } from '../../components/work/RiskFormModal'
import { RiskTable } from '../../components/work/RiskTable'
import { TaskFormModal } from '../../components/work/TaskFormModal'
import { TaskTable } from '../../components/work/TaskTable'
import { formatDateTime, formatDay } from '../../lib/format'
import { MILESTONE_STATE, enrolmentText } from '../../lib/studies'
import { EnrolmentCell } from './StudyPortfolioPage'

const TABS = ['milestones', 'sites', 'tasks', 'risks'] as const
type TabKey = (typeof TABS)[number]

/** /command-centre without a study: choose one. */
export function CommandCentreIndexPage() {
  const { data, isLoading } = useStudies()
  return (
    <>
      <PageHeader title="Study Command Centre" subtitle="Choose a study to open its workspace." />
      {data && <StudySourceBanner source={data.source} />}
      {isLoading ? (
        <Skeleton active />
      ) : (data?.studies.length ?? 0) === 0 ? (
        <Empty description="No studies have been synced from SimpleTrials yet." />
      ) : (
        <Row gutter={[16, 16]}>
          {data?.studies.map((s) => (
            <Col key={s.id} xs={24} md={12} xl={8}>
              <Link to={`/command-centre/${s.id}`} aria-label={`Open ${s.protocol_number}`}>
                <Card hoverable size="small" title={s.protocol_number} extra={s.status && <Tag>{s.status}</Tag>}>
                  <Typography.Paragraph ellipsis={{ rows: 2 }} style={{ marginBottom: 8 }}>
                    {s.title}
                  </Typography.Paragraph>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {[s.phase, s.sponsor].filter(Boolean).join(' · ')} · {s.open_tasks} open tasks ·{' '}
                    {s.open_risks} open risks
                  </Typography.Text>
                </Card>
              </Link>
            </Col>
          ))}
        </Row>
      )}
    </>
  )
}

export function StudyCommandCentrePage() {
  const { studyId } = useParams()
  const [params, setParams] = useSearchParams()
  const tabParam = params.get('tab') as TabKey | null
  const tab: TabKey = tabParam && TABS.includes(tabParam) ? tabParam : 'milestones'

  const study = useStudy(studyId)
  const tasks = useTasks({ study_id: studyId })
  const risks = useRisks({ study_id: studyId })
  const [taskModal, setTaskModal] = useState<{ open: boolean; task?: Task | null }>({ open: false })
  const [riskModal, setRiskModal] = useState<{ open: boolean; risk?: Risk | null }>({ open: false })

  if (study.isError) {
    const notFound = study.error instanceof ApiError && study.error.status === 404
    return (
      <Result
        status={notFound ? '404' : 'error'}
        title={notFound ? 'Study not found' : 'Could not load this study'}
        subTitle={notFound ? 'It may have been removed from SimpleTrials.' : study.error.message}
        extra={<Link to="/portfolio">Back to Study Portfolio</Link>}
      />
    )
  }
  if (!study.data) return <Skeleton active />

  const { study: s, sites, milestones, source, rules } = study.data
  const canManage = Boolean(tasks.data?.can_manage)

  const milestoneColumns = [
    { title: 'Milestone', dataIndex: 'name' },
    { title: 'Planned', dataIndex: 'planned_date', width: 140, render: (d: string | null) => formatDay(d) },
    { title: 'Actual', dataIndex: 'actual_date', width: 140, render: (d: string | null) => formatDay(d) },
    {
      title: 'State',
      dataIndex: 'state',
      width: 170,
      render: (_: unknown, m: Milestone) => (
        <ToneTag
          tone={MILESTONE_STATE[m.state]}
          help={
            m.state === 'overdue'
              ? rules.milestone_overdue
              : m.state === 'due_soon'
                ? rules.milestone_due_soon
                : undefined
          }
        />
      ),
    },
  ]

  const siteColumns = [
    { title: 'Site', dataIndex: 'site_number', width: 80 },
    {
      title: 'Name',
      dataIndex: 'name',
      render: (name: string, site: StudySite) => (
        <div>
          <div>{name}</div>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {[site.principal_investigator, site.country].filter(Boolean).join(' · ')}
          </Typography.Text>
        </div>
      ),
    },
    { title: 'Status', dataIndex: 'status', width: 150, render: (v: string | null) => (v ? <Tag>{v}</Tag> : '—') },
    {
      title: 'Activated',
      dataIndex: 'activation_date',
      width: 130,
      responsive: ['md' as const],
      render: (d: string | null) => formatDay(d),
    },
    {
      title: 'Enrolment',
      key: 'enrolment',
      width: 200,
      render: (_: unknown, site: StudySite) => <EnrolmentCell study={site} />,
    },
  ]

  return (
    <>
      <PageHeader
        title={`${s.protocol_number} · ${s.title}`}
        breadcrumbs={[{ title: 'Study Command Centre', to: '/command-centre' }, { title: s.protocol_number }]}
        extra={<ProvenanceTag kind="record" source={source.connector.mode === 'mock' ? 'Demo' : 'SimpleTrials'} />}
      />
      <StudySourceBanner source={source} />
      {!s.in_source && (
        <Alert
          type="error"
          showIcon
          style={{ marginBottom: 16 }}
          title="This study no longer appears in SimpleTrials"
          description="Its last synced details are shown. Linked tasks and risks are kept."
        />
      )}

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} xl={10}>
          <Card title="Key information" size="small" style={{ height: '100%' }}>
            <Descriptions
              column={1}
              size="small"
              items={[
                { key: 'sponsor', label: 'Sponsor', children: s.sponsor ?? '—' },
                { key: 'phase', label: 'Phase', children: s.phase ?? '—' },
                { key: 'ta', label: 'Therapeutic area', children: s.therapeutic_area ?? '—' },
                { key: 'status', label: 'Status', children: s.status ?? '—' },
                { key: 'countries', label: 'Countries', children: s.countries.join(', ') || '—' },
                { key: 'pm', label: 'Project manager', children: s.project_manager ?? '—' },
                { key: 'synced', label: 'Synced', children: formatDateTime(s.synced_at) },
              ]}
            />
          </Card>
        </Col>
        <Col xs={24} xl={14}>
          <Row gutter={[16, 16]}>
            {[
              { label: 'Sites', value: s.site_count },
              {
                label: 'Enrolment',
                value: enrolmentText(s.enrolled, s.enrolment_target, s.enrolment_percent),
                help: rules.enrolment,
              },
              { label: 'Overdue milestones', value: s.overdue_milestones, help: rules.milestone_overdue },
              { label: 'Open tasks', value: s.open_tasks },
              { label: 'Open risks and issues', value: s.open_risks },
            ].map((stat) => (
              <Col key={stat.label} xs={12} md={8}>
                <Card size="small">
                  <Statistic
                    title={stat.help ? <Tooltip title={stat.help}>{stat.label}</Tooltip> : stat.label}
                    value={stat.value}
                    styles={{ content: { fontSize: typeof stat.value === 'string' ? 16 : 24 } }}
                  />
                </Card>
              </Col>
            ))}
          </Row>
        </Col>
      </Row>

      <Card>
        <Tabs
          activeKey={tab}
          onChange={(key) => {
            const next = new URLSearchParams(params)
            next.set('tab', key)
            setParams(next, { replace: true })
          }}
          items={[
            {
              key: 'milestones',
              label: `Milestones (${milestones.length})`,
              children: (
                <Table<Milestone>
                  rowKey="id"
                  size="middle"
                  pagination={false}
                  columns={milestoneColumns}
                  dataSource={milestones}
                  locale={{ emptyText: <Empty description="SimpleTrials has no milestones for this study." /> }}
                />
              ),
            },
            {
              key: 'sites',
              label: `Sites (${sites.length})`,
              children: (
                <Table<StudySite>
                  rowKey="id"
                  size="middle"
                  pagination={false}
                  columns={siteColumns}
                  dataSource={sites}
                  locale={{ emptyText: <Empty description="SimpleTrials has no sites for this study." /> }}
                />
              ),
            },
            {
              key: 'tasks',
              label: `Tasks (${s.open_tasks})`,
              children: (
                <>
                  <Flex justify="space-between" align="center" wrap gap={8} style={{ marginBottom: 12 }}>
                    <Typography.Text type="secondary">
                      Open tasks for this study. Only the assigned person can change a task&apos;s status.
                    </Typography.Text>
                    {canManage && (
                      <Button type="primary" icon={<PlusOutlined />} onClick={() => setTaskModal({ open: true })}>
                        New task
                      </Button>
                    )}
                  </Flex>
                  <TaskTable
                    tasks={tasks.data?.tasks ?? []}
                    loading={tasks.isLoading}
                    canManage={canManage}
                    onEdit={(task) => setTaskModal({ open: true, task })}
                    emptyText="No open tasks for this study."
                  />
                </>
              ),
            },
            {
              key: 'risks',
              label: `Risks and issues (${s.open_risks})`,
              children: (
                <>
                  <Flex justify="space-between" align="center" wrap gap={8} style={{ marginBottom: 12 }}>
                    <Typography.Text type="secondary">{rules.risk_score}</Typography.Text>
                    {canManage && (
                      <Button type="primary" icon={<PlusOutlined />} onClick={() => setRiskModal({ open: true })}>
                        Raise risk or issue
                      </Button>
                    )}
                  </Flex>
                  <RiskTable
                    risks={risks.data?.risks ?? []}
                    loading={risks.isLoading}
                    canManage={canManage}
                    onEdit={(risk) => setRiskModal({ open: true, risk })}
                    emptyText="No open risks or issues for this study."
                    scoreRule={rules.risk_score}
                  />
                </>
              ),
            },
          ]}
        />
      </Card>

      <TaskFormModal
        open={taskModal.open}
        task={taskModal.task}
        defaultStudyId={s.id}
        onClose={() => setTaskModal({ open: false })}
      />
      <RiskFormModal
        open={riskModal.open}
        risk={riskModal.risk}
        defaultStudyId={s.id}
        onClose={() => setRiskModal({ open: false })}
      />
    </>
  )
}
