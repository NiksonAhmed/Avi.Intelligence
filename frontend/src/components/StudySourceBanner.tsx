import { CloudSyncOutlined } from '@ant-design/icons'
import { Alert, Flex, Typography } from 'antd'

import type { StudySource } from '../api/types'
import { formatDateTime } from '../lib/format'
import { ProvenanceTag } from './ProvenanceTag'
import { SyncNowButton } from './SyncNowButton'

/** States where study data came from and when it was last synced; flags demo data. */
export function StudySourceBanner({ source }: { source: StudySource }) {
  const synced = source.last_successful_sync_at
  const failed = source.last_sync && !source.last_sync.ok

  const syncButton = <SyncNowButton kind="simpletrials" />

  return (
    <>
      {source.connector.mode === 'mock' ? (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          title="Demo data: SimpleTrials is not connected"
          description={
            <>
              These studies, sites and people are fictional and are not Avion data.{' '}
              {source.connector.mock_reason}
            </>
          }
          action={syncButton}
        />
      ) : (
        <Flex align="center" justify="space-between" wrap gap={8} style={{ marginBottom: 16 }} role="status">
          <Flex align="center" gap={8} wrap>
            <ProvenanceTag kind="record" source="SimpleTrials" />
            <Typography.Text type="secondary">
              <CloudSyncOutlined /> Last synced {synced ? formatDateTime(synced) : 'never'}
              {source.connector.scope === 'study' && ' · single-study API access'}
            </Typography.Text>
          </Flex>
          {syncButton}
        </Flex>
      )}
      {failed && (
        <Alert
          type="error"
          showIcon
          style={{ marginBottom: 16 }}
          title="The last SimpleTrials sync failed"
          description={`${source.last_sync?.error ?? ''} Data shown is from the last successful sync${
            synced ? ` (${formatDateTime(synced)})` : ''
          }.`}
        />
      )}
    </>
  )
}
