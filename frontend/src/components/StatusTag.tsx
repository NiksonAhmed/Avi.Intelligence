import {
  CheckCircleFilled,
  ClockCircleOutlined,
  EditOutlined,
  MinusCircleOutlined,
  QuestionCircleOutlined,
  StopOutlined,
} from '@ant-design/icons'
import { Tag, Tooltip } from 'antd'
import type { CSSProperties, ReactNode } from 'react'

import type { SopStatus, StatusSource } from '../api/types'
import { STATUS_SOURCE_TEXT } from '../lib/sops'

/**
 * Status is always shown with an icon and text, never colour alone (WCAG 1.4.1).
 * Text colours meet WCAG AA contrast (≥ 4.5:1) against their backgrounds.
 */
const STATUS_STYLE: Record<SopStatus, { icon: ReactNode; style: CSSProperties }> = {
  Effective: {
    icon: <CheckCircleFilled />,
    style: { color: '#0F5B36', background: '#E6F4EC', borderColor: '#9CD1B4' },
  },
  'In Review': {
    icon: <ClockCircleOutlined />,
    style: { color: '#1A4475', background: '#E8F0FB', borderColor: '#A9C4EA' },
  },
  Draft: {
    icon: <EditOutlined />,
    style: { color: '#7A4A00', background: '#FDF3E1', borderColor: '#EDC98A' },
  },
  Superseded: {
    icon: <MinusCircleOutlined />,
    style: { color: '#3E4C5E', background: '#EEF1F5', borderColor: '#C9D1DC' },
  },
  Retired: {
    icon: <StopOutlined />,
    style: { color: '#3E4C5E', background: '#EEF1F5', borderColor: '#C9D1DC' },
  },
  Unknown: {
    icon: <QuestionCircleOutlined />,
    style: { color: '#3E4C5E', background: '#FFFFFF', borderColor: '#C9D1DC', borderStyle: 'dashed' },
  },
}

interface Props {
  status: SopStatus
  source?: StatusSource
}

export function StatusTag({ status, source }: Props) {
  const { icon, style } = STATUS_STYLE[status]
  const inferred = source === 'version-number'
  const tag = (
    <Tag icon={icon} style={{ ...style, marginInlineEnd: 0, fontWeight: 500 }}>
      {status}
      {inferred ? ' (inferred)' : ''}
    </Tag>
  )
  return source ? (
    <Tooltip title={STATUS_SOURCE_TEXT[source]}>
      <span style={{ display: 'inline-flex', width: 'fit-content' }}>{tag}</span>
    </Tooltip>
  ) : (
    tag
  )
}
