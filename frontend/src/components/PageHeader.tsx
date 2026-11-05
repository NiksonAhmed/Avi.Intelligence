import { Breadcrumb, Flex, Typography } from 'antd'
import type { ReactNode } from 'react'
import { Link } from 'react-router'

interface Crumb {
  title: string
  to?: string
}

interface Props {
  title: ReactNode
  subtitle?: ReactNode
  breadcrumbs?: Crumb[]
  extra?: ReactNode
}

export function PageHeader({ title, subtitle, breadcrumbs, extra }: Props) {
  return (
    <div style={{ marginBottom: 20 }}>
      {breadcrumbs && breadcrumbs.length > 0 && (
        <Breadcrumb
          style={{ marginBottom: 8 }}
          items={breadcrumbs.map((c) => ({
            key: c.title,
            title: c.to ? <Link to={c.to}>{c.title}</Link> : c.title,
          }))}
        />
      )}
      <Flex justify="space-between" align="flex-start" gap={16} wrap>
        <div style={{ minWidth: 0 }}>
          <Typography.Title level={2} style={{ margin: 0, fontSize: 24 }}>
            {title}
          </Typography.Title>
          {subtitle && (
            <Typography.Paragraph type="secondary" style={{ margin: '4px 0 0' }}>
              {subtitle}
            </Typography.Paragraph>
          )}
        </div>
        {extra && (
          <Flex gap={8} wrap>
            {extra}
          </Flex>
        )}
      </Flex>
    </div>
  )
}
