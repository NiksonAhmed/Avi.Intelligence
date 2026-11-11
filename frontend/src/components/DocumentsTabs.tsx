import { Tabs } from 'antd'
import { useNavigate } from 'react-router'

const TABS = [
  { key: 'sops', label: 'SOPs', path: '/documents/sops' },
  { key: 'ask', label: 'Ask Avi.Intelligence', path: '/documents/ask' },
  { key: 'templates', label: 'Templates (coming next)', disabled: true },
  { key: 'study', label: 'Study documents (coming next)', disabled: true },
]

export function DocumentsTabs({ active }: { active: 'sops' | 'ask' }) {
  const navigate = useNavigate()
  return (
    <Tabs
      activeKey={active}
      onChange={(key) => {
        const tab = TABS.find((t) => t.key === key)
        if (tab?.path) void navigate(tab.path)
      }}
      items={TABS.map(({ key, label, disabled }) => ({ key, label, disabled }))}
    />
  )
}
