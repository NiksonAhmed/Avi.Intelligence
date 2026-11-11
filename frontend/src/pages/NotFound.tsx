import { Button, Result } from 'antd'
import { Link } from 'react-router'

export function NotFound() {
  return (
    <Result
      status="404"
      title="Page not found"
      extra={
        <Link to="/">
          <Button type="primary">Go to Overview</Button>
        </Link>
      }
    />
  )
}
