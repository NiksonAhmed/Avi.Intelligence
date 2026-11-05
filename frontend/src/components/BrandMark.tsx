interface Props {
  collapsed?: boolean
}

/** Product wordmark for the navy sidebar. */
export function BrandMark({ collapsed = false }: Props) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: '#fff' }}>
      <svg width="30" height="30" viewBox="0 0 32 32" aria-hidden="true" focusable="false">
        <path d="M16 3 L29 28 H22.5 L16 15 L9.5 28 H3 Z" fill="#FFFFFF" />
        <path d="M16 19 L19.5 26 H12.5 Z" fill="#7FA7E0" />
      </svg>
      {!collapsed && (
        <div style={{ lineHeight: 1.1 }}>
          <div style={{ fontWeight: 700, fontSize: 17, letterSpacing: 0.3 }}>Avi.Intelligence</div>
          <div style={{ fontSize: 11, opacity: 0.7 }}>Smarter clinical trial operations.</div>
        </div>
      )}
    </div>
  )
}
