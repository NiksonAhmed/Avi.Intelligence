// Australia outline for the Site validation map. Generated from approximate coastline points (hand-placed,
// public geography; no map service). Equirectangular, longitude scaled by cos 28°.
export const AU_WIDTH = 1000
export const AU_HEIGHT = 951
const KX = 23.26
const KY = 26.43

/** Position of a latitude/longitude on the map, as a fraction of its width and height (0–1). */
export function auPoint(lat: number, lon: number): { x: number; y: number } {
  return { x: ((lon - 112) * KX) / AU_WIDTH, y: ((-lat - 9) * KY) / AU_HEIGHT }
}

export const AU_LAND = 'M709.4,44.9 L732.7,92.5 L739.7,132.2 L774.6,158.6 L779.2,208.8 L797.8,261.7 L856.0,298.7 L888.5,351.5 L918.8,396.4 L956.0,430.8 L967.6,507.5 L953.7,581.5 L942.0,621.1 L911.8,658.1 L888.5,705.7 L881.6,753.3 L825.7,766.5 L797.8,795.5 L765.3,774.4 L732.7,787.6 L674.5,769.1 L644.3,745.3 L635.0,703.0 L607.1,703.0 L616.4,681.9 L602.4,634.3 L590.8,684.5 L579.2,695.1 L597.8,650.2 L581.5,639.6 L555.9,684.5 L539.6,660.8 L516.4,631.7 L446.6,594.7 L395.4,600.0 L325.6,615.8 L269.8,658.1 L230.3,658.1 L139.6,687.2 L69.8,668.7 L83.7,642.2 L86.1,605.2 L67.5,528.6 L34.9,462.5 L39.5,396.4 L44.2,343.6 L109.3,306.6 L158.2,298.7 L209.3,277.5 L237.3,237.9 L267.5,198.2 L302.4,158.6 L348.9,132.2 L383.8,155.9 L409.4,155.9 L418.7,105.7 L437.3,89.9 L479.2,60.8 L535.0,84.6 L576.8,84.6 L558.2,118.9 L546.6,158.6 L593.1,190.3 L635.0,222.0 L669.9,222.0 L686.2,158.6 L688.5,92.5 Z M758.3,837.8 L802.5,848.4 L844.3,843.1 L844.3,877.5 L832.7,903.9 L811.8,914.5 L788.5,911.8 L772.2,877.5 Z'

export const AU_BORDERS = 'M395.4,155.9 L395.4,600.0 M604.8,200.9 L604.8,449.3 M395.4,449.3 L674.5,449.3 M674.5,449.3 L674.5,769.1 M674.5,528.6 L967.6,507.5 M674.5,660.8 L744.3,711.0 L814.1,713.6 L881.6,753.3'

export const AU_STATES = [
  { label: 'WA', x: 221, y: 436 },
  { label: 'NT', x: 500, y: 291 },
  { label: 'SA', x: 535, y: 542 },
  { label: 'QLD', x: 768, y: 370 },
  { label: 'NSW', x: 802, y: 608 },
  { label: 'VIC', x: 809, y: 756 },
  { label: 'TAS', x: 805, y: 877 },
]
