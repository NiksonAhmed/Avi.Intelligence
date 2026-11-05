import { DownloadOutlined, ExportOutlined, WarningOutlined } from '@ant-design/icons'
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
  Table,
  Tag,
  Typography,
} from 'antd'
import { Link, useParams } from 'react-router'

import { ApiError, sopDownloadUrl } from '../../api/client'
import { useHasPermission, useSop } from '../../api/hooks'
import type { SopVersion } from '../../api/types'
import { PageHeader } from '../../components/PageHeader'
import { ProvenanceTag } from '../../components/ProvenanceTag'
import { StatusTag } from '../../components/StatusTag'
import { formatBytes, formatDate, formatDateTime } from '../../lib/format'
import { STATUS_SOURCE_TEXT } from '../../lib/sops'

const crumbs = [
  { title: 'Documents and Knowledge', to: '/documents/sops' },
  { title: 'SOPs', to: '/documents/sops' },
]

export function SopDetailPage() {
  const { sopId = '' } = useParams()
  const { data, isLoading, isError, error } = useSop(sopId)
  const canDownload = useHasPermission('sop.download')

  if (isLoading) {
    return (
      <>
        <PageHeader title="Loading SOP…" breadcrumbs={crumbs} />
        <Card>
          <Skeleton active paragraph={{ rows: 8 }} />
        </Card>
      </>
    )
  }

  if (isError || !data) {
    const notFound = error instanceof ApiError && (error.status === 404 || error.status === 422)
    return (
      <Result
        status={notFound ? '404' : 'error'}
        title={notFound ? 'SOP not found' : 'Could not load this SOP'}
        subTitle={
          notFound
            ? 'It may have been moved or removed from the SOP library in SharePoint.'
            : error?.message
        }
        extra={
          <Link to="/documents/sops">
            <Button type="primary">Back to SOPs</Button>
          </Link>
        }
      />
    )
  }

  const { document: doc, versions, review_due: reviewDue, source } = data
  const isDemo = source.mode === 'mock'

  return (
    <>
      <PageHeader
        breadcrumbs={[...crumbs, { title: doc.sop_number ?? doc.title }]}
        title={
          <Flex align="center" gap={12} wrap>
            <span>
              {doc.sop_number ? `${doc.sop_number} · ` : ''}
              {doc.title}
            </span>
            <StatusTag status={doc.status} source={doc.status_source} />
          </Flex>
        }
        subtitle={doc.file_name}
        extra={
          <>
            {canDownload && (
              <Button type="primary" icon={<DownloadOutlined />} href={sopDownloadUrl(doc.id)}>
                {isDemo ? 'Download demo file' : 'Download'}
              </Button>
            )}
            {doc.web_url && (
              <Button
                icon={<ExportOutlined />}
                href={doc.web_url}
                target="_blank"
                rel="noopener noreferrer"
              >
                Open in SharePoint
              </Button>
            )}
          </>
        }
      />

      {isDemo && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          title="Demo record: not an Avion controlled document"
          description={source.mock_reason}
        />
      )}
      {doc.status !== 'Effective' && doc.status !== 'Unknown' && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          title={`This SOP is ${doc.status.toLowerCase()}.`}
          description="Use only the effective version of a procedure for study work."
        />
      )}

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={16}>
          <Card
            title="Key information"
            extra={<ProvenanceTag kind="record" source={isDemo ? 'Demo data' : 'SharePoint'} />}
          >
            <Descriptions
              column={{ xs: 1, sm: 2 }}
              size="middle"
              items={[
                { key: 'num', label: 'SOP number', children: doc.sop_number ?? '—' },
                { key: 'ver', label: 'Version', children: doc.version ?? '—' },
                {
                  key: 'status',
                  label: 'Status',
                  children: (
                    <Flex vertical gap={4} align="flex-start">
                      <StatusTag status={doc.status} source={doc.status_source} />
                      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                        {STATUS_SOURCE_TEXT[doc.status_source]}
                      </Typography.Text>
                    </Flex>
                  ),
                },
                { key: 'dept', label: 'Department', children: doc.department ?? '—' },
                { key: 'eff', label: 'Effective date', children: formatDate(doc.effective_date) },
                {
                  key: 'rev',
                  label: 'Next review',
                  children: (
                    <Flex gap={6} align="center">
                      {formatDate(doc.review_date)}
                      {reviewDue && (
                        <Tag color="warning" icon={<WarningOutlined />}>
                          Review due
                        </Tag>
                      )}
                    </Flex>
                  ),
                },
                { key: 'owner', label: 'Owner', children: doc.owner ?? '—' },
                { key: 'folder', label: 'Library folder', children: doc.folder_path || '(library root)' },
                {
                  key: 'mod',
                  label: 'Last modified',
                  children: `${formatDateTime(doc.modified_at)}${doc.modified_by ? ` by ${doc.modified_by}` : ''}`,
                },
                { key: 'size', label: 'File size', children: formatBytes(doc.size_bytes) },
              ]}
            />
          </Card>
        </Col>
        <Col xs={24} xl={8}>
          <Card title="Version history" extra={<ProvenanceTag kind="record" />}>
            <Table<SopVersion>
              rowKey="id"
              size="small"
              pagination={false}
              dataSource={versions}
              locale={{ emptyText: <Empty description="No version history available." /> }}
              columns={[
                { title: 'Version', dataIndex: 'id', width: 80 },
                {
                  title: 'Saved',
                  dataIndex: 'modified_at',
                  render: (v: string | null) => formatDate(v),
                },
                { title: 'By', dataIndex: 'modified_by', render: (v: string | null) => v ?? '—' },
              ]}
            />
          </Card>
        </Col>
      </Row>
    </>
  )
}
