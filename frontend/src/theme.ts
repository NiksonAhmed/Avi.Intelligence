import type { ThemeConfig } from 'antd'

/** Avi.Intelligence visual identity: navy and white with restrained accents. */
export const brand = {
  navy900: '#0A1F3C',
  navy800: '#0F2A4F',
  navy700: '#163A6B',
  primary: '#1F4E8C',
  surface: '#F4F6FA',
  border: '#E3E8F0',
  textMuted: '#5B6B82',
} as const

export const theme: ThemeConfig = {
  token: {
    colorPrimary: brand.primary,
    colorInfo: brand.primary,
    colorSuccess: '#1E7F4F',
    colorWarning: '#B26B00',
    colorError: '#B42318',
    colorBgLayout: brand.surface,
    colorBorderSecondary: brand.border,
    colorTextSecondary: brand.textMuted,
    borderRadius: 8,
    fontFamily:
      "'Segoe UI', 'Inter', system-ui, -apple-system, 'Helvetica Neue', Arial, sans-serif",
    fontSize: 14,
  },
  components: {
    Layout: {
      siderBg: brand.navy900,
      headerBg: '#FFFFFF',
      headerHeight: 64,
      headerPadding: '0 24px',
    },
    Menu: {
      darkItemBg: brand.navy900,
      darkSubMenuItemBg: brand.navy900,
      darkItemSelectedBg: brand.navy700,
      darkItemColor: 'rgba(255,255,255,0.78)',
      darkItemHoverColor: '#FFFFFF',
    },
    Table: {
      headerBg: '#F8FAFC',
      headerColor: brand.textMuted,
    },
    Card: {
      headerFontSize: 15,
    },
  },
}
