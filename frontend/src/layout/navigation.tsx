import {
  AlertOutlined,
  AppstoreOutlined,
  AuditOutlined,
  BarChartOutlined,
  CheckSquareOutlined,
  DatabaseOutlined,
  DashboardOutlined,
  EnvironmentOutlined,
  FolderOpenOutlined,
  GlobalOutlined,
  MessageOutlined,
  ProjectOutlined,
  SettingOutlined,
} from '@ant-design/icons'
import type { ReactNode } from 'react'

export type NavGroup = 'studies' | 'knowledge' | 'business' | 'admin'

export interface NavItem {
  key: string
  path: string
  label: string
  icon: ReactNode
  /** The menu heading it sits under; none for the top items (Overview, My Tasks, Ask). */
  group?: NavGroup
  /** Shown only to users with this permission. */
  permission?: string
  /** Shown only while this optional module is switched on. */
  module?: 'data-management' | 'conferences'
}

export const NAV_GROUPS: { key: NavGroup; label: string }[] = [
  { key: 'studies', label: 'Studies' },
  { key: 'knowledge', label: 'Knowledge' },
  { key: 'business', label: 'Business' },
  { key: 'admin', label: 'Admin' },
]

/**
 * Main navigation (user decision 2026-11-16): the daily items first, then grouped by subject. The same
 * order for everyone; each person sees only the items their role allows.
 */
export const NAV_ITEMS: NavItem[] = [
  { key: 'overview', path: '/', label: 'Overview', icon: <DashboardOutlined /> },
  { key: 'tasks', path: '/tasks', label: 'My Tasks', icon: <CheckSquareOutlined />, permission: 'task.view' },
  { key: 'ask', path: '/ask', label: 'Ask Avi.Intelligence', icon: <MessageOutlined />, permission: 'assistant.use' },
  {
    key: 'portfolio',
    path: '/portfolio',
    label: 'Study Portfolio',
    icon: <AppstoreOutlined />,
    group: 'studies',
    permission: 'portfolio.read',
  },
  {
    key: 'command-centre',
    path: '/command-centre',
    label: 'Study Command Centre',
    icon: <ProjectOutlined />,
    group: 'studies',
    permission: 'study.read',
  },
  {
    key: 'site-validation',
    path: '/site-validation',
    label: 'Site validation',
    icon: <EnvironmentOutlined />,
    group: 'studies',
    permission: 'site_validation.view',
  },
  { key: 'risks', path: '/risks', label: 'Risks and Issues', icon: <AlertOutlined />, group: 'studies', permission: 'study.read' },
  {
    key: 'reports',
    path: '/reports',
    label: 'Reports and Insights',
    icon: <BarChartOutlined />,
    group: 'studies',
    permission: 'study.read',
  },
  {
    key: 'data-management',
    path: '/data-management',
    label: 'Data Management',
    icon: <DatabaseOutlined />,
    group: 'studies',
    permission: 'dm.view',
    module: 'data-management',
  },
  {
    key: 'documents',
    path: '/documents',
    label: 'Documents and Knowledge',
    icon: <FolderOpenOutlined />,
    group: 'knowledge',
    permission: 'sop.read',
  },
  {
    key: 'conferences',
    path: '/conferences',
    label: 'Conferences',
    icon: <GlobalOutlined />,
    group: 'business',
    permission: 'conference.view',
    module: 'conferences',
  },
  { key: 'admin', path: '/admin', label: 'Administration', icon: <SettingOutlined />, group: 'admin', permission: 'connector.manage' },
  { key: 'audit', path: '/audit', label: 'Audit Trail', icon: <AuditOutlined />, group: 'admin', permission: 'audit.read' },
]

export function activeNavKey(pathname: string): string {
  if (pathname === '/') return 'overview'
  const match = NAV_ITEMS.filter((i) => i.path !== '/' && pathname.startsWith(i.path))
  return match[0]?.key ?? ''
}
