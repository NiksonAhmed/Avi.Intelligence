import { Flex, Table, Tag, Typography } from 'antd'
import type { HTMLAttributes } from 'react'

import type { SimpleTrialsIssue } from '../../api/types'
import { formatDay } from '../../lib/format'

interface Props {
  issues: SimpleTrialsIssue[]
  loading?: boolean
  /** Show the study column (the cross-study register). */
  showStudy?: boolean
}

const PRIORITY_COLOUR: Record<string, string> = { High: 'red', Urgent: 'red', Normal: 'blue', Low: 'default' }

/** SimpleTrials action items as read-only issues: they are managed in SimpleTrials, not here. */
export function SimpleTrialsIssues({ issues, loading, showStudy }: Props) {
  return (
    <Flex vertical gap={8} data-testid="simpletrials-issues">
      <Flex align="center" gap={8} wrap>
        <Typography.Title level={5} style={{ margin: 0 }}>
          From SimpleTrials
        </Typography.Title>
        <Tag color="blue">Read-only</Tag>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Action items from SimpleTrials, shown as issues. Update them in SimpleTrials; changes appear after the next sync.
        </Typography.Text>
      </Flex>
      <Table<SimpleTrialsIssue>
        size="small"
        rowKey="id"
        loading={loading}
        dataSource={issues}
        pagination={issues.length > 20 ? { pageSize: 20, showSizeChanger: false } : false}
        scroll={{ x: 900 }}
        locale={{ emptyText: 'No open SimpleTrials action items.' }}
        onRow={() => ({ 'data-testid': 'simpletrials-issue-row' }) as HTMLAttributes<HTMLElement>}
        columns={[
          { title: 'No.', dataIndex: 'number', width: 60, render: (v: string | null) => v ?? '—' },
          ...(showStudy ? [{ title: 'Study', key: 'study', width: 130, render: (_: unknown, r: SimpleTrialsIssue) => r.study.protocol_number }] : []),
          {
            title: 'Site',
            key: 'site',
            width: 160,
            render: (_, r) => (r.site_number ? `${r.site_number}${r.site_name ? ` · ${r.site_name}` : ''}` : <Typography.Text type="secondary">Study level</Typography.Text>),
          },
          {
            title: 'Action item',
            key: 'description',
            render: (_, r) => (
              <Flex vertical gap={2}>
                <span>{r.description ?? '—'}</span>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {[r.category, r.subcategory].filter(Boolean).join(' · ')}
                  {r.response ? ` · Response: ${r.response}` : ''}
                </Typography.Text>
              </Flex>
            ),
          },
          {
            title: 'Priority',
            dataIndex: 'priority',
            width: 90,
            render: (v: string | null) => (v ? <Tag color={PRIORITY_COLOUR[v] ?? 'default'}>{v}</Tag> : '—'),
          },
          { title: 'Assigned to', dataIndex: 'assignee', width: 140, render: (v: string | null) => v ?? '—' },
          {
            title: 'Due',
            key: 'due',
            width: 150,
            render: (_, r) => (
              <Flex vertical gap={0}>
                <span>{r.due_on ? formatDay(r.due_on) : '—'}</span>
                {r.days_overdue !== null && (
                  <Typography.Text type="danger" style={{ fontSize: 12 }} data-testid="simpletrials-issue-overdue">
                    {r.days_overdue} day{r.days_overdue === 1 ? '' : 's'} overdue
                  </Typography.Text>
                )}
              </Flex>
            ),
          },
          {
            title: 'Status',
            key: 'status',
            width: 110,
            render: (_, r) => (r.closed ? <Tag>{r.status ?? 'Closed'}</Tag> : <Tag color="gold">{r.status ?? 'Open'}</Tag>),
          },
        ]}
      />
    </Flex>
  )
}
