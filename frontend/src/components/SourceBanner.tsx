import { CloudSyncOutlined, SyncOutlined } from '@ant-design/icons'
import { Alert, Button, Flex, Typography } from 'antd'

import type { SopSource } from '../api/types'
import { formatDateTime } from '../lib/format'
import { ProvenanceTag } from './ProvenanceTag'

interface Props {
  source: SopSource
  fetchedAt?: string
  fromCache?: boolean
  onRefresh?: () => void
  refreshing?: boolean
}

/** States plainly where the data on screen came from, and flags demo data. */
export function SourceBanner({ source, fetchedAt, fromCache, onRefresh, refreshing }: Props) {
  if (source.mode === 'mock') {
    return (
      <Alert
        type="warning"
        showIcon
        style={{ marginBottom: 16 }}
        title="Demo data: SharePoint is not connected"
        description={
          <>
            These SOPs are sample records for demonstration only and are not Avion controlled
            documents. {source.mock_reason}
          </>
        }
      />
    )
  }
  const location = [source.library, source.folder].filter(Boolean).join(' / ')
  return (
    <Flex
      align="center"
      justify="space-between"
      wrap
      gap={8}
      style={{ marginBottom: 16 }}
      role="status"
    >
      <Flex align="center" gap={8} wrap>
        <ProvenanceTag kind="record" source="SharePoint" />
        <Typography.Text type="secondary">
          <CloudSyncOutlined /> {location}
          {fetchedAt && ` · Retrieved ${formatDateTime(fetchedAt)}${fromCache ? ' (cached)' : ''}`}
        </Typography.Text>
      </Flex>
      {onRefresh && (
        <Button icon={<SyncOutlined />} onClick={onRefresh} loading={refreshing}>
          Sync now
        </Button>
      )}
    </Flex>
  )
}
