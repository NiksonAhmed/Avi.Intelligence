import { PlusOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Checkbox, Flex, Segmented, Typography } from 'antd'
import { useState } from 'react'
import { useSearchParams } from 'react-router'

import { useRisks } from '../../api/hooks'
import type { Risk, RiskKind } from '../../api/types'
import { PageHeader } from '../../components/PageHeader'
import { RiskFormModal } from '../../components/work/RiskFormModal'
import { RiskTable } from '../../components/work/RiskTable'
import { SimpleTrialsIssues } from '../../components/work/SimpleTrialsIssues'

const SCORE_RULE =
  'Score: likelihood × impact as entered by the risk owner (1 = low, 3 = high). 6 or more is High, 3–4 Medium, 1–2 Low.'

export function RisksPage() {
  const [params, setParams] = useSearchParams()
  const kindParam = params.get('kind')
  const kind: RiskKind | undefined = kindParam === 'risk' || kindParam === 'issue' ? kindParam : undefined
  const mine = params.get('owner') === 'me'
  const includeClosed = params.get('closed') === '1'
  const { data, isLoading, isError, error, refetch } = useRisks({
    kind,
    owner: mine ? 'me' : undefined,
    include_closed: includeClosed,
  })
  const [modal, setModal] = useState<{ open: boolean; risk?: Risk | null }>({ open: false })

  const setParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }
  const canManage = Boolean(data?.can_manage)

  return (
    <>
      <PageHeader
        title="Risks and Issues"
        subtitle="Risk and issue register across all studies, highest score first."
        extra={
          canManage && (
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setModal({ open: true })}>
              Raise risk or issue
            </Button>
          )
        }
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
          <Segmented
            aria-label="Type"
            value={kind ?? 'all'}
            onChange={(v) => setParam('kind', v === 'all' ? null : String(v))}
            options={[
              { value: 'all', label: 'All' },
              { value: 'risk', label: 'Risks' },
              { value: 'issue', label: 'Issues' },
            ]}
          />
          <Checkbox checked={mine} onChange={(e) => setParam('owner', e.target.checked ? 'me' : null)}>
            Owned by me
          </Checkbox>
          <Checkbox checked={includeClosed} onChange={(e) => setParam('closed', e.target.checked ? '1' : null)}>
            Show closed
          </Checkbox>
        </Flex>
        <Typography.Paragraph type="secondary">
          {SCORE_RULE} Only the owner can update a status; only an administrator can raise or edit.
        </Typography.Paragraph>
        <RiskTable
          risks={data?.risks ?? []}
          loading={isLoading}
          canManage={canManage}
          showStudy
          onEdit={(risk) => setModal({ open: true, risk })}
          emptyText="No open risks or issues."
          scoreRule={SCORE_RULE}
        />
      </Card>
      {kind !== 'risk' && !mine && (
        <Card style={{ marginTop: 16 }}>
          <SimpleTrialsIssues issues={data?.simpletrials_issues ?? []} loading={isLoading} showStudy />
        </Card>
      )}
      <RiskFormModal open={modal.open} risk={modal.risk} onClose={() => setModal({ open: false })} />
    </>
  )
}
