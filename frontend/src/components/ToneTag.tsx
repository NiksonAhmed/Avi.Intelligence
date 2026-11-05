import { Tag, Tooltip } from 'antd'
import type { ReactNode } from 'react'

import type { ToneStyle } from '../lib/studies'

interface Props {
  tone: ToneStyle
  icon?: ReactNode
  help?: string
  children?: ReactNode
}

/** A status label that always carries text (never colour alone), optionally explained by a tooltip. */
export function ToneTag({ tone, icon, help, children }: Props) {
  const tag = (
    <Tag
      icon={icon}
      style={{
        color: tone.color,
        background: tone.background,
        borderColor: tone.border,
        marginInlineEnd: 0,
        fontWeight: 500,
      }}
    >
      {children ?? tone.label}
    </Tag>
  )
  return help ? (
    <Tooltip title={help}>
      <span style={{ display: 'inline-flex', width: 'fit-content' }}>{tag}</span>
    </Tooltip>
  ) : (
    tag
  )
}
