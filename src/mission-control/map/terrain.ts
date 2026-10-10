// Procedural lunar basemap. ILLUSTRATIVE ONLY — it is not survey data and carries no telemetry meaning.
// Deterministic hillshaded height field (fbm + craters) generated in 16 m chunks in LOCAL_ENU_V1 meters,
// so it pans/zooms with the grid. Low sun from the west, matching the intro's lighting.

export const CHUNK_M = 16
const RES = 128 // samples per chunk edge (8 px per meter)

function hash2(ix: number, iy: number, seed: number) {
  let h = (Math.imul(ix, 374761393) + Math.imul(iy, 668265263) + Math.imul(seed, 1442695041)) | 0
  h = Math.imul(h ^ (h >>> 13), 1274126177)
  h ^= h >>> 16
  return (h >>> 0) / 4294967295
}
function vnoise(x: number, y: number, seed: number) {
  const ix = Math.floor(x), iy = Math.floor(y)
  const fx = x - ix, fy = y - iy
  const u = fx * fx * (3 - 2 * fx), v = fy * fy * (3 - 2 * fy)
  const a = hash2(ix, iy, seed), b = hash2(ix + 1, iy, seed), c = hash2(ix, iy + 1, seed), d = hash2(ix + 1, iy + 1, seed)
  return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v
}
function fbm(x: number, y: number, oct: number, seed: number) {
  let s = 0, a = 0.5, f = 1
  for (let i = 0; i < oct; i++) { s += a * vnoise(x * f, y * f, seed + i * 17); f *= 2.03; a *= 0.5 }
  return s
}
function rng(seed: number) {
  let t = seed >>> 0
  return () => {
    t += 0x6d2b79f5
    let r = Math.imul(t ^ (t >>> 15), 1 | t)
    r ^= r + Math.imul(r ^ (r >>> 7), 61 | r)
    return ((r ^ (r >>> 14)) >>> 0) / 4294967296
  }
}

type Crater = { x: number; y: number; r: number; depth: number }
const craterCache = new Map<string, Crater[]>()
function cratersFor(cx: number, cy: number): Crater[] {
  const k = cx + ',' + cy
  const cached = craterCache.get(k)
  if (cached) return cached
  const r = rng(Math.floor(hash2(cx, cy, 991) * 4294967295))
  const list: Crater[] = []
  const n = Math.floor(r() * 5)
  for (let i = 0; i < n; i++) {
    const rad = 0.25 + Math.pow(r(), 3) * 3.4
    list.push({ x: cx * CHUNK_M + r() * CHUNK_M, y: cy * CHUNK_M + r() * CHUNK_M, r: rad, depth: rad * 0.24 })
  }
  if (r() < 0.16) { const rad = 4 + r() * 3.5; list.push({ x: cx * CHUNK_M + r() * CHUNK_M, y: cy * CHUNK_M + r() * CHUNK_M, r: rad, depth: rad * 0.18 }) }
  craterCache.set(k, list)
  if (craterCache.size > 4000) craterCache.delete(craterCache.keys().next().value as string)
  return list
}

const SUN = (() => { const v = [-0.86, 0.22, 0.46]; const l = Math.hypot(v[0], v[1], v[2]); return v.map((c) => c / l) })()

/** Render one chunk (cx, cy in chunk units) into a RES×RES canvas. Row 0 is the chunk's north edge. */
export function renderTerrainChunk(cx: number, cy: number): HTMLCanvasElement {
  const near: Crater[] = []
  for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) near.push(...cratersFor(cx + dx, cy + dy))
  const N = RES + 2
  const step = CHUNK_M / RES
  const x0 = cx * CHUNK_M, yTop = (cy + 1) * CHUNK_M
  const H = new Float32Array(N * N)
  const A = new Float32Array(N * N)
  for (let j = 0; j < N; j++) {
    const y = yTop - (j - 0.5) * step
    for (let i = 0; i < N; i++) {
      const x = x0 + (i - 0.5) * step
      let h = fbm(x * 0.04, y * 0.04, 4, 11) * 2.4 + fbm(x * 0.55, y * 0.55, 3, 29) * 0.14 + vnoise(x * 3.1, y * 3.1, 5) * 0.025
      for (let c = 0; c < near.length; c++) {
        const cr = near[c]
        const ddx = x - cr.x, ddy = y - cr.y
        const d2 = (ddx * ddx + ddy * ddy) / (cr.r * cr.r)
        if (d2 > 3) continue
        const d = Math.sqrt(d2)
        if (d < 1) h -= cr.depth * (1 - d2)
        h += cr.depth * 0.38 * Math.exp(-(((d - 1) / 0.24) ** 2))
      }
      H[j * N + i] = h
      A[j * N + i] = 0.72 + 0.4 * fbm(x * 0.18 + 40, y * 0.18, 2, 71)
    }
  }
  const cv = document.createElement('canvas')
  cv.width = RES; cv.height = RES
  const g = cv.getContext('2d')
  if (!g) return cv
  const img = g.createImageData(RES, RES)
  const d = img.data
  for (let j = 1; j <= RES; j++) {
    for (let i = 1; i <= RES; i++) {
      const dhdx = (H[j * N + i + 1] - H[j * N + i - 1]) / (2 * step)
      const dhdy = (H[(j - 1) * N + i] - H[(j + 1) * N + i]) / (2 * step)
      const nl = Math.hypot(dhdx, dhdy, 1)
      const lam = Math.max(0, (-dhdx * SUN[0] - dhdy * SUN[1] + SUN[2]) / nl)
      const v = Math.min(1, 0.035 + Math.pow(lam, 1.25) * 0.5 * A[j * N + i])
      const o = ((j - 1) * RES + (i - 1)) * 4
      d[o] = v * 228; d[o + 1] = v * 233; d[o + 2] = v * 242; d[o + 3] = 255
    }
  }
  g.putImageData(img, 0, 0)
  return cv
}
