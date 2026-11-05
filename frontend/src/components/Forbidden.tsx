import { Result } from 'antd'

export function Forbidden({ what }: { what: string }) {
  return (
    <Result
      status="403"
      title="You don't have access"
      subTitle={`Your role does not include permission to view ${what}. Contact an administrator if you need access.`}
    />
  )
}
