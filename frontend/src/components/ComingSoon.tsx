import { Card, Empty, Typography } from 'antd'

import { PageHeader } from './PageHeader'

interface Props {
  title: string
  description: string
}

/** Honest placeholder for sections not built yet: no sample numbers, no fake charts. */
export function ComingSoon({ title, description }: Props) {
  return (
    <>
      <PageHeader title={title} />
      <Card>
        <Empty
          description={
            <>
              <Typography.Text strong>Not available yet</Typography.Text>
              <br />
              <Typography.Text type="secondary">{description}</Typography.Text>
            </>
          }
        />
      </Card>
    </>
  )
}
