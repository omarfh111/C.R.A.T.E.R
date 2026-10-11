import type { TrailPoint } from '../model/types'

export const MINIMAP_SIZE = 160
export type MapPoint = { x: number; y: number }

/** A square, north-up overview. Both axes use the same meters-per-pixel scale. */
export function miniMapProjection(points: readonly MapPoint[]) {
  let x0 = 0, x1 = 0, y0 = 0, y1 = 0
  for (const p of points) {
    x0 = Math.min(x0, p.x); x1 = Math.max(x1, p.x)
    y0 = Math.min(y0, p.y); y1 = Math.max(y1, p.y)
  }
  const spanM = Math.max(12, x1 - x0, y1 - y0) * 1.25
  const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2
  const scale = MINIMAP_SIZE / spanM
  return {
    spanM, scale,
    project: (p: MapPoint): MapPoint => ({ x: MINIMAP_SIZE / 2 + (p.x - cx) * scale, y: MINIMAP_SIZE / 2 - (p.y - cy) * scale }),
  }
}

/** A skipped sequence is shown separately as an unobserved, dashed connection. */
export function miniMapTrail(trail: readonly TrailPoint[], project: (p: MapPoint) => MapPoint) {
  let observed = '', gaps = ''
  for (let i = 1; i < trail.length; i++) {
    const a = project(trail[i - 1]), b = project(trail[i])
    const segment = `M${a.x},${a.y}L${b.x},${b.y}`
    if (trail[i].gap > 0) gaps += segment
    else observed += segment
  }
  return { observed, gaps }
}
