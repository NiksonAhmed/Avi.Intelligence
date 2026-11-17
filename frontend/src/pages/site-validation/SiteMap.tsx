import type { CSSProperties } from 'react'

import { AU_BORDERS, AU_HEIGHT, AU_LAND, AU_STATES, AU_WIDTH, auPoint } from './australiaMap'
import './SiteValidationPage.css'

/** One site on the map: its colour, whether it pulses, and the lines in its city tag. */
export interface MapPin {
  id: string
  city: string
  lat: number
  lon: number
  colour: string
  attention: boolean
  ariaLabel: string
  lines: { text: string; className?: string }[]
}

const pct = (v: number) => `${(v * 100).toFixed(2)}%`
// Where each city tag sits next to its pin; close neighbours go above and below so tags never overlap.
const RIGHT = 'translate(14px, -50%)'
const LABEL_AT: Record<string, string> = {
  Brisbane: 'translate(14px, -105%)',
  'Gold Coast': 'translate(14px, 5%)',
  Newcastle: 'translate(calc(-100% - 14px), -50%)',
  Adelaide: 'translate(14px, -105%)',
  Sydney: 'translate(14px, 5%)',
  Melbourne: 'translate(calc(-100% - 14px), -105%)',
  Geelong: 'translate(calc(-100% - 14px), 5%)',
  Canberra: 'translate(calc(-100% - 14px), -50%)',
}

/** The solid purple map of Australia with glowing site pins (Site validation and Site feasibility). */
export function AustraliaMap({ pins, onSelect, selected }: { pins: MapPin[]; onSelect: (id: string) => void; selected?: string }) {
  return (
    <div
      role="img"
      aria-label={`Map of Australia with ${pins.length} sites`}
      data-testid="site-map"
      style={{ position: 'relative', width: '100%', maxWidth: 860, margin: '0 auto', aspectRatio: `${AU_WIDTH} / ${AU_HEIGHT}` }}
    >
      <svg viewBox={`0 0 ${AU_WIDTH} ${AU_HEIGHT}`} aria-hidden="true" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}>
        <defs>
          <filter id="sv-glow" x="-10%" y="-10%" width="120%" height="120%">
            <feGaussianBlur stdDeviation="10" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        <path d={AU_LAND} fill="#7463E8" stroke="#8F80F5" strokeWidth={2} strokeLinejoin="round" filter="url(#sv-glow)" />
        <path d={AU_BORDERS} fill="none" stroke="#5A49C9" strokeWidth={2} strokeLinecap="round" />
        {AU_STATES.map((s) => (
          <text key={s.label} x={s.x} y={s.y} textAnchor="middle" fontSize={22} fontWeight={700} fill="#E4DFFF" opacity={0.75} letterSpacing={3}>
            {s.label}
          </text>
        ))}
      </svg>
      {pins.map((s) => {
        const p = auPoint(s.lat, s.lon)
        const at: CSSProperties = { position: 'absolute', left: pct(p.x), top: pct(p.y) }
        const on = selected === s.id
        return (
          <span key={s.id}>
            {s.attention && <span className="sv-ring" aria-hidden="true" style={{ ...at, borderColor: s.colour }} />}
            <button
              type="button"
              className="sv-pin"
              data-testid="site-pin"
              aria-label={s.ariaLabel}
              aria-pressed={on}
              onClick={() => onSelect(s.id)}
              style={{
                ...at,
                width: on ? 18 : 13,
                height: on ? 18 : 13,
                boxShadow: `0 0 0 3px ${s.colour}, 0 0 14px 5px ${s.colour}${on ? ', 0 0 0 8px rgba(255,255,255,0.35)' : ''}`,
              }}
            />
            <span aria-hidden="true" className="sv-label" style={{ ...at, transform: LABEL_AT[s.city] ?? RIGHT, borderColor: `${s.colour}66` }}>
              <strong>{s.city}</strong>
              {s.lines.map((l, i) => (
                <small key={i} className={l.className}>
                  {l.text}
                </small>
              ))}
            </span>
          </span>
        )
      })}
    </div>
  )
}
