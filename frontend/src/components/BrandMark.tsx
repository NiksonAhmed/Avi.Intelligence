import avionLogo from '../assets/avion-logo.png'

/**
 * Avion logo (transparent PNG with blue lettering) on a white panel so it keeps its brand
 * colours and contrast against the navy sidebar, followed by the product name.
 */
export function BrandMark() {
  return (
    <div>
      <div
        style={{
          background: '#FFFFFF',
          borderRadius: 8,
          padding: '10px 12px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <img src={avionLogo} alt="Avion" style={{ width: '100%', height: 'auto', display: 'block' }} />
      </div>
      <div style={{ color: '#FFFFFF', marginTop: 12, lineHeight: 1.2 }}>
        <div style={{ fontWeight: 700, fontSize: 16, letterSpacing: 0.3 }}>Avi.Intelligence</div>
        <div style={{ fontSize: 11, opacity: 0.75 }}>Smarter clinical trial operations.</div>
      </div>
    </div>
  )
}
