import { BellOutlined, MenuOutlined } from '@ant-design/icons'
import {
  Avatar,
  Button,
  Dropdown,
  Empty,
  Flex,
  Input,
  Layout,
  Menu,
  Popover,
  Tag,
  Typography,
} from 'antd'
import { useState } from 'react'
import { Link, Outlet, useLocation, useNavigate } from 'react-router'

import { useMe } from '../api/hooks'
import { BrandMark } from '../components/BrandMark'
import { initials } from '../lib/format'
import { brand } from '../theme'
import { NAV_ITEMS, activeNavKey } from './navigation'

const { Sider, Header, Content } = Layout

function NotificationCentre() {
  // No notification source exists yet; show an honest empty state rather than sample alerts.
  return (
    <Popover
      trigger="click"
      placement="bottomRight"
      title="Notifications"
      content={
        <div style={{ width: 280 }}>
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="No notifications yet. Task and milestone alerts will appear here."
          />
        </div>
      }
    >
      <Button
        type="text"
        shape="circle"
        aria-label="Notifications"
        icon={<BellOutlined style={{ fontSize: 18 }} />}
      />
    </Popover>
  )
}

function UserMenu() {
  const { data: me } = useMe()
  const name = me?.name ?? 'Loading…'
  return (
    <Dropdown
      trigger={['click']}
      menu={{
        items: [
          { key: 'role', label: <span>Role: <strong>{me?.role_label ?? '—'}</strong></span>, disabled: true },
          {
            key: 'auth',
            label:
              me?.auth_mode === 'development'
                ? 'Development sign-in (Microsoft sign-in comes later)'
                : 'Signed in with Microsoft',
            disabled: true,
          },
        ],
      }}
    >
      <Button type="text" style={{ height: 48 }} aria-label={`User menu for ${name}`}>
        <Flex align="center" gap={10}>
          <Avatar style={{ background: brand.primary }}>{me ? initials(me.name) : ''}</Avatar>
          <span style={{ textAlign: 'left', lineHeight: 1.2 }} className="hide-on-tablet">
            <Typography.Text strong style={{ display: 'block' }}>{name}</Typography.Text>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>{me?.role_label}</Typography.Text>
          </span>
        </Flex>
      </Button>
    </Dropdown>
  )
}

export function AppLayout() {
  const location = useLocation()
  const navigate = useNavigate()
  const [collapsed, setCollapsed] = useState(false)
  const [narrow, setNarrow] = useState(false)
  const { data: me } = useMe()

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <a href="#main-content" className="skip-link">Skip to main content</a>
      <Sider
        width={248}
        breakpoint="lg"
        collapsedWidth={0}
        collapsed={collapsed}
        onBreakpoint={(broken) => {
          setNarrow(broken)
          setCollapsed(broken)
        }}
        trigger={null}
        style={narrow ? { position: 'fixed', height: '100vh', zIndex: 20, left: 0, top: 0 } : undefined}
      >
        <div style={{ padding: '20px 20px 24px' }}>
          <Link to="/" aria-label="Avi.Intelligence home">
            <BrandMark />
          </Link>
        </div>
        <nav aria-label="Main navigation">
          <Menu
            theme="dark"
            mode="inline"
            selectedKeys={[activeNavKey(location.pathname)]}
            items={NAV_ITEMS.map((item) => ({
              key: item.key,
              icon: item.icon,
              label: <Link to={item.path}>{item.label}</Link>,
            }))}
            onClick={() => narrow && setCollapsed(true)}
          />
        </nav>
      </Sider>
      {narrow && !collapsed && (
        <div className="sider-backdrop" onClick={() => setCollapsed(true)} aria-hidden="true" />
      )}
      <Layout>
        <Header style={{ borderBottom: `1px solid ${brand.border}`, position: 'sticky', top: 0, zIndex: 10 }}>
          <Flex align="center" justify="space-between" gap={16} style={{ height: '100%' }}>
            <Flex align="center" gap={12} style={{ flex: 1, minWidth: 0 }}>
              {narrow && (
                <Button
                  type="text"
                  icon={<MenuOutlined />}
                  aria-label={collapsed ? 'Open navigation' : 'Close navigation'}
                  aria-expanded={!collapsed}
                  onClick={() => setCollapsed((c) => !c)}
                />
              )}
              <Input.Search
                placeholder="Search SOPs by number, title or department"
                aria-label="Global search"
                allowClear
                style={{ maxWidth: 440 }}
                onSearch={(value) => {
                  const q = value.trim()
                  void navigate(q ? `/documents/sops?q=${encodeURIComponent(q)}` : '/documents/sops')
                }}
              />
            </Flex>
            <Flex align="center" gap={8}>
              {me?.auth_mode === 'development' && (
                <Tag color="gold" className="hide-on-tablet">Development mode</Tag>
              )}
              <NotificationCentre />
              <UserMenu />
            </Flex>
          </Flex>
        </Header>
        <Content id="main-content" tabIndex={-1} style={{ padding: 24, outline: 'none' }}>
          <div style={{ maxWidth: 1400, margin: '0 auto' }}>
            <Outlet />
          </div>
        </Content>
      </Layout>
    </Layout>
  )
}
