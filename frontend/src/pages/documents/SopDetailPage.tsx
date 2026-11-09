import { DownloadOutlined, ExportOutlined, FileWordOutlined, WarningOutlined } from '@ant-design/icons'
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
import type { RevisionEntry, SopDocument } from '../../api/types'
import { PageHeader } from '../../components/PageHeader'
import { ProvenanceTag } from '../../components/ProvenanceTag'
import { StatusTag } from '../../components/StatusTag'
import { SopTasksCard } from '../../components/work/SopTasksCard'
import { formatBytes, formatDate, formatDateTime, formatDay } from '../../lib/format'
import { STATUS_SOURCE_TEXT, downloadOptions } from '../../lib/sops'

const VERSION_SOURCE_TEXT = {
  column: "From the library's version column in SharePoint.",
  document: "From the document's cover page.",
  'file-name': 'From the file name.',
} as const

/** Forms/templates: Word first (most people fill them in), the filed PDF alongside. */
function DownloadButtons({ doc, size = 'middle' }: { doc: SopDocument; size?: 'small' | 'middle' }) {
  const options = downloadOptions(doc)
  const name = doc.sop_number ?? doc.title
  return (
    <Flex gap={6}>
      {options.word && (
        <Button
          type="primary"
          size={size}
          icon={<FileWordOutlined />}
          href={sopDownloadUrl(doc.id, 'word')}
          aria-label={`Download ${name} as Word`}
        >
          Word
        </Button>
      )}
      {options.original && (
        <Button
          size={size}
          type={options.word ? 'default' : 'primary'}
          icon={<DownloadOutlined />}
          href={sopDownloadUrl(doc.id)}
          aria-label={`Download ${name} as ${options.originalLabel}`}
        >
          {options.originalLabel}
        </Button>
      )}
    </Flex>
  )
}

function signOff(name: string | null, date: string | null) {
  if (!name && !date) return '—'
  return [name, date ? formatDay(date) : null].filter(Boolean).join(', ')
}

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

  const { document: doc, forms, parent, review_due: reviewDue, source } = data
  const isDemo = source.mode === 'mock'
  const isForm = doc.kind === 'form'
  const details = doc.details ?? null

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
            {canDownload &&
              (isDemo ? (
                <Button type="primary" icon={<DownloadOutlined />} href={sopDownloadUrl(doc.id)}>
                  Download demo file
                </Button>
              ) : isForm ? (
                <DownloadButtons doc={doc} />
              ) : (
                <Button type="primary" icon={<DownloadOutlined />} href={sopDownloadUrl(doc.id)}>
                  Download
                </Button>
              ))}
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
          title={`This ${isForm ? 'form' : 'SOP'} is ${doc.status.toLowerCase()}.`}
          description="Use only the effective version of a procedure for study work."
        />
      )}

      <Row gutter={[16, 16]}>
        <Col span={24}>
          <Card
            title="Key information"
            extra={<ProvenanceTag kind="record" source={isDemo ? 'Demo data' : 'SharePoint'} />}
          >
            <Descriptions
              column={{ xs: 1, sm: 2 }}
              size="middle"
              items={[
                { key: 'num', label: isForm ? 'Form number' : 'SOP number', children: doc.sop_number ?? '—' },
                ...(isForm
                  ? [
                      {
                        key: 'parent',
                        label: 'Belongs to SOP',
                        children: parent ? (
                          <Link to={`/documents/sops/${parent.id}`}>
                            {parent.sop_number} · {parent.title}
                          </Link>
                        ) : (
                          (doc.parent_sop_number ?? '—')
                        ),
                      },
                    ]
                  : []),
                {
                  key: 'ver',
                  label: 'Version',
                  children: (
                    <Flex vertical gap={4} align="flex-start">
                      <span>{doc.version ?? '—'}</span>
                      {doc.version_source && (
                        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                          {VERSION_SOURCE_TEXT[doc.version_source]}
                        </Typography.Text>
                      )}
                      {doc.file_name_version && (
                        <Tag color="warning" style={{ marginInlineEnd: 0 }}>
                          File name says {doc.file_name_version}
                        </Tag>
                      )}
                    </Flex>
                  ),
                },
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
                {
                  key: 'eff',
                  label: 'Effective date',
                  children: (
                    <Flex vertical gap={2} align="flex-start">
                      <span>{formatDate(doc.effective_date)}</span>
                      {!doc.effective_date && details && (
                        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                          Not stated on the document's cover
                          {details.approved_date ? ` (approved ${formatDay(details.approved_date)})` : ''}
                        </Typography.Text>
                      )}
                    </Flex>
                  ),
                },
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
                ...(details && (details.prepared_by || details.approved_by || details.approved_date)
                  ? [
                      { key: 'prep', label: 'Prepared by', children: signOff(details.prepared_by, details.prepared_date) },
                      { key: 'revd', label: 'Reviewed by', children: signOff(details.reviewed_by, details.reviewed_date) },
                      { key: 'appr', label: 'Approved by', children: signOff(details.approved_by, details.approved_date) },
                    ]
                  : [{ key: 'owner', label: 'Owner', children: doc.owner ?? '—' }]),
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
          {details && (
            <Card
              title="Change history"
              style={{ marginTop: 16 }}
              extra={<ProvenanceTag kind="record" source="From the document" />}
            >
              <Table<RevisionEntry>
                rowKey={(r) => `${r.version}-${r.issued ?? ''}`}
                size="small"
                pagination={false}
                dataSource={details.revisions}
                locale={{ emptyText: <Empty description="No change history table was found in the document." /> }}
                columns={[
                  { title: 'Version', dataIndex: 'version', width: 90 },
                  {
                    title: 'Date of issue',
                    dataIndex: 'issued',
                    width: 130,
                    render: (v: string | null) => (v ? formatDay(v) : '—'),
                  },
                  { title: 'Changes', dataIndex: 'changes', render: (v: string) => v || '—' },
                ]}
              />
            </Card>
          )}
          {!isForm && (
            <Card
              title={`Forms and templates (${forms.length})`}
              style={{ marginTop: 16 }}
              extra={<ProvenanceTag kind="record" source={isDemo ? 'Demo data' : 'SharePoint'} />}
            >
              <Table<SopDocument>
                rowKey="id"
                size="small"
                pagination={false}
                dataSource={forms}
                locale={{ emptyText: <Empty description="No forms or templates are filed for this SOP." /> }}
                columns={[
                  {
                    title: 'No.',
                    dataIndex: 'sop_number',
                    width: 120,
                    render: (v: string | null, f) => <Link to={`/documents/sops/${f.id}`}>{v ?? '—'}</Link>,
                  },
                  {
                    title: 'Title',
                    dataIndex: 'title',
                    render: (t: string, f) => <Link to={`/documents/sops/${f.id}`}>{t}</Link>,
                  },
                  { title: 'Version', dataIndex: 'version', width: 90, render: (v: string | null) => v ?? '—' },
                  ...(canDownload
                    ? [
                        {
                          title: 'Download',
                          key: 'dl',
                          width: 180,
                          render: (_: unknown, f: SopDocument) => <DownloadButtons doc={f} size="small" />,
                        },
                      ]
                    : []),
                ]}
              />
            </Card>
          )}
          <SopTasksCard doc={doc} />
        </Col>
      </Row>
    </>
  )
}
