import {
  AlertOutlined,
  AppstoreOutlined,
  AuditOutlined,
  BarChartOutlined,
  CheckSquareOutlined,
  DashboardOutlined,
  FolderOpenOutlined,
  ProjectOutlined,
  SettingOutlined,
} from '@ant-design/icons'
import type { ReactNode } from 'react'

export interface NavItem {
  key: string
  path: string
  label: string
  icon: ReactNode
}

/** Main navigation, in the order defined by the product brief. */
export const NAV_ITEMS: NavItem[] = [
  { key: 'overview', path: '/', label: 'Overview', icon: <DashboardOutlined /> },
  { key: 'portfolio', path: '/portfolio', label: 'Study Portfolio', icon: <AppstoreOutlined /> },
  { key: 'command-centre', path: '/command-centre', label: 'Study Command Centre', icon: <ProjectOutlined /> },
  { key: 'tasks', path: '/tasks', label: 'My Tasks', icon: <CheckSquareOutlined /> },
  { key: 'risks', path: '/risks', label: 'Risks and Issues', icon: <AlertOutlined /> },
  { key: 'documents', path: '/documents', label: 'Documents and Knowledge', icon: <FolderOpenOutlined /> },
  { key: 'reports', path: '/reports', label: 'Reports and Insights', icon: <BarChartOutlined /> },
  { key: 'admin', path: '/admin', label: 'Administration', icon: <SettingOutlined /> },
  { key: 'audit', path: '/audit', label: 'Audit Trail', icon: <AuditOutlined /> },
]

export function activeNavKey(pathname: string): string {
  if (pathname === '/') return 'overview'
  const match = NAV_ITEMS.filter((i) => i.path !== '/' && pathname.startsWith(i.path))
  return match[0]?.key ?? ''
}
