import {
  CopyOutlined,
  FileTextOutlined,
  QuestionCircleOutlined,
  SafetyCertificateOutlined,
  SendOutlined,
} from '@ant-design/icons'
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Empty,
  Flex,
  Input,
  Row,
  Skeleton,
  Tag,
  Typography,
} from 'antd'
import { useState } from 'react'
import { Link } from 'react-router'

import { useAsk, useAssistantStatus } from '../../api/hooks'
import type { AskResponse, AssistantCitation, AssistantExcerpt } from '../../api/types'
import { DocumentsTabs } from '../../components/DocumentsTabs'
import { PageHeader } from '../../components/PageHeader'
import { ProvenanceTag } from '../../components/ProvenanceTag'
import { answerAsText, sopLabel } from '../../lib/assistant'
import { brand } from '../../theme'

interface Turn {
  question: string
  response: AskResponse
}

function CitationMarker({ n }: { n: number }) {
  return (
    <sup>
      <a href={`#citation-${n}`} aria-label={`Source ${n}`} style={{ fontWeight: 600, padding: '0 1px' }}>
        [{n}]
      </a>
    </sup>
  )
}

function SourceList({ citations }: { citations: AssistantCitation[] }) {
  return (
    <ol style={{ listStyle: 'none', padding: 0, margin: 0 }} aria-label="Source documents">
      {citations.map((c) => (
        <li
          key={c.number}
          id={`citation-${c.number}`}
          style={{ padding: '10px 12px', border: `1px solid ${brand.border}`, borderRadius: 8, marginBottom: 8 }}
        >
          <Flex gap={8} align="baseline" wrap>
            <Typography.Text strong>[{c.number}]</Typography.Text>
            <FileTextOutlined style={{ color: brand.primary }} />
            <Link to={`/documents/sops/${encodeURIComponent(c.sop_id)}`}>{sopLabel(c)}</Link>
            <Typography.Text type="secondary">· {c.section}</Typography.Text>
          </Flex>
          {c.cited_text && (
            <Typography.Paragraph
              type="secondary"
              ellipsis={{ rows: 3, expandable: true, symbol: 'more' }}
              style={{ margin: '6px 0 0', paddingLeft: 12, borderLeft: `3px solid ${brand.border}` }}
            >
              {c.cited_text}
            </Typography.Paragraph>
          )}
        </li>
      ))}
    </ol>
  )
}

function ExcerptList({ excerpts }: { excerpts: AssistantExcerpt[] }) {
  return (
    <Flex vertical gap={8}>
      {excerpts.map((e, i) => (
        <div key={`${e.sop_id}-${i}`} style={{ padding: '10px 12px', border: `1px solid ${brand.border}`, borderRadius: 8 }}>
          <Flex gap={8} align="baseline" wrap>
            <FileTextOutlined style={{ color: brand.primary }} />
            <Link to={`/documents/sops/${encodeURIComponent(e.sop_id)}`}>{sopLabel(e)}</Link>
            <Typography.Text type="secondary">· {e.section}</Typography.Text>
          </Flex>
          <Typography.Paragraph ellipsis={{ rows: 4, expandable: true, symbol: 'more' }} style={{ margin: '6px 0 0', whiteSpace: 'pre-line' }}>
            {e.text}
          </Typography.Paragraph>
        </div>
      ))}
    </Flex>
  )
}

function AnswerView({ turn }: { turn: Turn }) {
  const { message } = App.useApp()
  const r = turn.response
  const hasAnswer = r.segments.length > 0

  return (
    <Flex vertical gap={16}>
      <div>
        <Typography.Text type="secondary">Question</Typography.Text>
        <Typography.Paragraph strong style={{ margin: 0 }}>
          {turn.question}
        </Typography.Paragraph>
      </div>

      <Flex gap={8} wrap align="center">
        {hasAnswer && <ProvenanceTag kind="ai" source={r.model ?? 'Claude'} />}
        {hasAnswer && r.citations.length > 0 && (
          <Tag color="green" icon={<SafetyCertificateOutlined />} variant="outlined">
            Grounded in effective SOPs
          </Tag>
        )}
        {!hasAnswer && r.excerpts.length > 0 && <ProvenanceTag kind="record" source="SOP passages" />}
        {r.demo && <Tag color="gold">Demo SOPs</Tag>}
        {hasAnswer && (
          <Button
            size="small"
            icon={<CopyOutlined />}
            style={{ marginInlineStart: 'auto' }}
            onClick={() =>
              void navigator.clipboard
                .writeText(answerAsText(r))
                .then(() => message.success('Answer copied with sources'))
            }
          >
            Copy
          </Button>
        )}
      </Flex>

      {r.notice && (
        <Alert
          type={r.outcome === 'answered' && hasAnswer ? 'warning' : 'info'}
          showIcon
          title={r.notice}
        />
      )}

      {hasAnswer && (
        <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.65, fontSize: 15 }} aria-live="polite">
          {r.segments.map((s, i) => (
            <span key={i}>
              {s.text}
              {s.citations.map((n) => (
                <CitationMarker key={n} n={n} />
              ))}
            </span>
          ))}
        </div>
      )}

      {r.citations.length > 0 && (
        <div>
          <Typography.Title level={5}>Source documents</Typography.Title>
          <SourceList citations={r.citations} />
        </div>
      )}

      {r.excerpts.length > 0 && (
        <div>
          <Typography.Title level={5}>Most relevant SOP passages</Typography.Title>
          <ExcerptList excerpts={r.excerpts} />
        </div>
      )}

      {hasAnswer && (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          <QuestionCircleOutlined /> This answer was generated by AI from effective Avion SOPs only. Verify
          it against the source document before acting. If the information is insufficient, contact the SOP
          owner or your study lead.
        </Typography.Text>
      )}
    </Flex>
  )
}

export function AskPage() {
  const [question, setQuestion] = useState('')
  const [turns, setTurns] = useState<Turn[]>([])
  const [shown, setShown] = useState(0)
  const status = useAssistantStatus()
  const ask = useAsk()

  const submit = (q: string) => {
    const text = q.trim()
    if (text.length < 3 || ask.isPending) return
    setQuestion(text)
    ask.mutate(text, {
      onSuccess: (response) => {
        setTurns((prev) => [{ question: text, response }, ...prev])
        setShown(0)
      },
    })
  }

  const current = turns[shown]

  return (
    <>
      <PageHeader
        title="Documents and Knowledge"
        subtitle="Ask questions and get answers drawn only from Avion's effective SOPs, with sources."
      />
      <DocumentsTabs active="ask" />

      {status.data && !status.data.ai_enabled && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          title="AI answers are not switched on yet"
          description="Add an Anthropic API key (ANTHROPIC_API_KEY in .env) to enable written answers. Until then, questions return the most relevant SOP passages."
        />
      )}

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={9}>
          <Card title="Ask Avi.Intelligence">
            <form
              onSubmit={(e) => {
                e.preventDefault()
                submit(question)
              }}
            >
              <Input.TextArea
                aria-label="Your question"
                placeholder="e.g. What are the key requirements for site activation?"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) submit(question)
                }}
                autoSize={{ minRows: 3, maxRows: 8 }}
                maxLength={2000}
                showCount
              />
              <Flex justify="space-between" align="center" style={{ marginTop: 28 }} gap={8} wrap>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  Don't enter patient-identifiable information.
                </Typography.Text>
                <Button
                  type="primary"
                  htmlType="submit"
                  icon={<SendOutlined />}
                  loading={ask.isPending}
                  disabled={question.trim().length < 3}
                >
                  Ask
                </Button>
              </Flex>
            </form>

            {status.data && status.data.suggested_questions.length > 0 && (
              <div style={{ marginTop: 20 }}>
                <Typography.Text strong>Suggested questions</Typography.Text>
                <Flex vertical gap={6} style={{ marginTop: 8 }}>
                  {status.data.suggested_questions.map((q) => (
                    <Button
                      key={q}
                      onClick={() => submit(q)}
                      style={{ justifyContent: 'flex-start', textAlign: 'left', height: 'auto', whiteSpace: 'normal', padding: '6px 12px' }}
                    >
                      {q}
                    </Button>
                  ))}
                </Flex>
              </div>
            )}

            {turns.length > 1 && (
              <div style={{ marginTop: 20 }}>
                <Typography.Text strong>Earlier in this session</Typography.Text>
                <Flex vertical gap={4} style={{ marginTop: 8 }}>
                  {turns.map((t, i) => (
                    <Button
                      key={t.response.interaction_id}
                      type={i === shown ? 'primary' : 'text'}
                      ghost={i === shown}
                      onClick={() => setShown(i)}
                      style={{ justifyContent: 'flex-start', textAlign: 'left', height: 'auto', whiteSpace: 'normal' }}
                    >
                      {t.question}
                    </Button>
                  ))}
                </Flex>
              </div>
            )}

            {status.data && (
              <Typography.Paragraph type="secondary" style={{ fontSize: 12, marginTop: 20, marginBottom: 0 }}>
                {status.data.documents > 0
                  ? `Searching ${status.data.documents} effective SOPs (${status.data.passages} passages).`
                  : 'The SOP index is built the first time someone asks a question.'}{' '}
                Draft, in-review and superseded SOPs are never used.
              </Typography.Paragraph>
            )}
          </Card>
        </Col>

        <Col xs={24} xl={15}>
          <Card title="Answer">
            {ask.isPending ? (
              <div role="status">
                <Typography.Text type="secondary">Searching SOPs and preparing an answer…</Typography.Text>
                <Skeleton active paragraph={{ rows: 6 }} style={{ marginTop: 12 }} />
              </div>
            ) : ask.isError && !current ? (
              <Alert type="error" showIcon title="Could not answer" description={ask.error.message} />
            ) : current ? (
              <>
                {ask.isError && (
                  <Alert type="error" showIcon style={{ marginBottom: 16 }} title="Could not answer" description={ask.error.message} />
                )}
                <AnswerView turn={current} />
              </>
            ) : (
              <Empty description="Ask a question about Avion SOPs. Answers cite the SOP and section they come from." />
            )}
          </Card>
        </Col>
      </Row>
    </>
  )
}
