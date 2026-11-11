import { SyncOutlined } from '@ant-design/icons'
import { Alert, App, Button, Card, Descriptions, Table, Tag, Typography } from 'antd'

import { useAssistantStatus, useReindex } from '../../api/hooks'
import type { ReindexResponse } from '../../api/types'
import { formatDateTime } from '../../lib/format'

type IndexedDoc = ReindexResponse['documents'][number]

export function AssistantAdminCard() {
  const status = useAssistantStatus()
  const reindex = useReindex()
  const { message } = App.useApp()
  const s = status.data

  return (
    <Card
      title="AI assistant: SOP knowledge index"
      style={{ marginTop: 16 }}
      extra={
        s && (
          <Tag color={s.ai_enabled ? 'success' : 'warning'}>
            {s.ai_enabled ? 'AI answers on' : 'Search-only (no API key)'}
          </Tag>
        )
      }
    >
      <Descriptions
        size="small"
        column={{ xs: 1, md: 2 }}
        items={[
          { key: 'model', label: 'Model', children: s?.model ?? 'Not configured' },
          { key: 'docs', label: 'Effective SOPs indexed', children: s?.documents ?? '—' },
          { key: 'passages', label: 'Passages', children: s?.passages ?? '—' },
          { key: 'failed', label: 'Could not be read', children: s?.failed ?? '—' },
          { key: 'when', label: 'Last indexed', children: formatDateTime(s?.last_indexed_at) },
        ]}
      />
      <Typography.Paragraph type="secondary" style={{ marginTop: 12 }}>
        Only SOPs with status Effective are indexed. Re-index after SOPs are published or superseded in
        SharePoint; unchanged documents are skipped.
      </Typography.Paragraph>
      <Button
        icon={<SyncOutlined />}
        loading={reindex.isPending}
        onClick={() =>
          reindex.mutate(undefined, {
            onSuccess: (r) =>
              void message.success(
                `Index updated: ${r.indexed} indexed, ${r.unchanged} unchanged, ${r.removed} removed`,
              ),
            onError: (e) => void message.error(e.message),
          })
        }
      >
        Re-index SOPs now
      </Button>

      {reindex.data && reindex.data.failed.length > 0 && (
        <Alert
          type="warning"
          showIcon
          style={{ marginTop: 16 }}
          title={`${reindex.data.failed.length} SOP(s) could not be read`}
          description="Scanned PDFs and legacy .doc files cannot be indexed. Save them as .docx or text-based PDF."
        />
      )}
      {reindex.data && (
        <Table<IndexedDoc>
          style={{ marginTop: 16 }}
          size="small"
          rowKey={(d) => `${d.sop_number}-${d.title}`}
          pagination={{ pageSize: 10, hideOnSinglePage: true }}
          dataSource={reindex.data.documents}
          columns={[
            { title: 'SOP', dataIndex: 'sop_number', render: (v: string | null) => v ?? '—' },
            { title: 'Title', dataIndex: 'title' },
            { title: 'Version', dataIndex: 'version', render: (v: string | null) => v ?? '—' },
            { title: 'Passages', dataIndex: 'passages' },
            {
              title: 'Result',
              dataIndex: 'error',
              render: (e: string | null) => (e ? <Tag color="error">{e}</Tag> : <Tag color="success">Indexed</Tag>),
            },
          ]}
        />
      )}
    </Card>
  )
}
