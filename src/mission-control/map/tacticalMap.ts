// Tactical map renderer (Canvas 2D). World units: meters in LOCAL_ENU_V1 (x east, y north, origin = mission start marker).
// Every marker is drawn at its accepted telemetry coordinate. The basemap (terrain.ts) is illustrative only.
import { HAZARD_STYLE } from '../model/constants'
import type { HazardType, MapModel } from '../model/types'
import { CHUNK_M, renderTerrainChunk } from './terrain'

const CYAN = '155,221,234'
const AMBER = '242,181,74'
const RED = '239,91,76'
const MONO = '"IBM Plex Mono", ui-monospace, monospace'
const MAX_CHUNKS = 220
const MIN_SCALE = 9 // px per meter
const MAX_SCALE = 240

export type TacticalMapCallbacks = {
  onHover?: (key: string | null) => void
  onSelect?: (key: string | null) => void
  onCursor?: (world: { x: number; y: number } | null) => void
  onFollowChange?: (follow: boolean) => void
  onFrame?: (info: { scale: number }) => void
}
export type TacticalMapApi = {
  setFollow: (v: boolean) => void
  reboot: () => void
  zoomBy: (factor: number) => void
  centerOn: (x: number, y: number) => void
  fit: (points: { x: number; y: number }[]) => void
  destroy: () => void
}

const ease = (t: number) => (t < 0 ? 0 : t > 1 ? 1 : 1 - Math.pow(1 - t, 3))
function niceStep(minWorld: number) {
  const steps = [0.25, 0.5, 1, 2, 5, 10, 20, 50, 100, 200]
  return steps.find((s) => s >= minWorld) ?? 500
}
function fmt(n: number) {
  const s = Math.abs(n) < 1e-6 ? '0' : Number.isInteger(n) ? String(Math.abs(n)) : Math.abs(n).toFixed(1)
  return (n > 0 ? '+' : n < 0 ? '−' : '') + s
}
function glyph(ctx: CanvasRenderingContext2D, type: HazardType, x: number, y: number, size: number, color: string, filled: boolean) {
  ctx.beginPath()
  if (type === 'crater') ctx.arc(x, y, size, 0, Math.PI * 2)
  else if (type === 'rock') { ctx.moveTo(x, y - size * 1.15); ctx.lineTo(x + size * 1.15, y); ctx.lineTo(x, y + size * 1.15); ctx.lineTo(x - size * 1.15, y); ctx.closePath() }
  else if (type === 'slope') { ctx.moveTo(x, y - size * 1.2); ctx.lineTo(x + size * 1.15, y + size * 0.85); ctx.lineTo(x - size * 1.15, y + size * 0.85); ctx.closePath() }
  else ctx.rect(x - size * 0.9, y - size * 0.9, size * 1.8, size * 1.8)
  if (filled) { ctx.fillStyle = color; ctx.fill() }
  ctx.strokeStyle = color
  ctx.stroke()
}

export function createTacticalMap(canvas: HTMLCanvasElement, getModel: () => MapModel, cb: TacticalMapCallbacks): TacticalMapApi {
  const context = canvas.getContext('2d')
  if (!context) throw new Error('Canvas 2D unavailable')
  const ctx = context
  const chunks = new Map<string, HTMLCanvasElement>()
  let W = 0, H = 0, dpr = 1
  const view = { cx: 4, cy: 0, s: 34 }
  const target = { cx: 4, cy: 0, s: 34 }
  let initialScaleSet = false
  let follow = true
  let raf = 0
  let timeout = 0
  let destroyed = false
  let drag: { x: number; y: number; cx: number; cy: number; moved: boolean } | null = null
  let hoverKey: string | null = null
  let lastRover: { x: number; y: number } | null = null
  let roverAnim: { seq: number; fx: number; fy: number; tx: number; ty: number; t0: number } | null = null
  let lastPulseSeq = -1
  const pulses: { t0: number; late: boolean }[] = []
  let bootStart = performance.now()
  let grain: CanvasPattern | null = null
  const reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
  let lastDraw = -Infinity

  function resize() {
    const r = canvas.getBoundingClientRect()
    dpr = Math.min(2, window.devicePixelRatio || 1)
    W = Math.max(1, r.width); H = Math.max(1, r.height)
    if (W < 2) return
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr)
    if (!initialScaleSet) { view.s = target.s = Math.max(18, W / 30); initialScaleSet = true }
  }
  const ro = new ResizeObserver(() => resize())
  ro.observe(canvas)
  resize()

  const toScreen = (x: number, y: number): [number, number] => [W / 2 + (x - view.cx) * view.s, H / 2 - (y - view.cy) * view.s]
  const toWorld = (sx: number, sy: number): [number, number] => [view.cx + (sx - W / 2) / view.s, view.cy - (sy - H / 2) / view.s]

  function makeGrain() {
    const c = document.createElement('canvas'); c.width = c.height = 160
    const g = c.getContext('2d')
    if (!g) return null
    const im = g.createImageData(160, 160)
    for (let i = 0; i < im.data.length; i += 4) { const v = Math.random() * 255; im.data[i] = im.data[i + 1] = im.data[i + 2] = v; im.data[i + 3] = 255 }
    g.putImageData(im, 0, 0)
    return ctx.createPattern(c, 'repeat')
  }

  function hitTest(sx: number, sy: number) {
    const m = getModel()
    let best: string | null = null, bd = 16
    for (const h of m.hazards) {
      if (!m.filters[h.type]) continue
      const [x, y] = toScreen(h.x, h.y)
      const d = Math.hypot(x - sx, y - sy)
      if (d < bd) { bd = d; best = h.key }
    }
    return best
  }

  function setFollow(v: boolean) { if (follow !== v) { follow = v; cb.onFollowChange?.(v) } }

  function onDown(e: PointerEvent) {
    canvas.setPointerCapture(e.pointerId)
    drag = { x: e.clientX, y: e.clientY, cx: target.cx, cy: target.cy, moved: false }
  }
  function onMove(e: PointerEvent) {
    const r = canvas.getBoundingClientRect()
    const sx = e.clientX - r.left, sy = e.clientY - r.top
    if (drag) {
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y
      if (Math.hypot(dx, dy) > 4) drag.moved = true
      if (drag.moved) {
        setFollow(false)
        target.cx = drag.cx - dx / view.s; target.cy = drag.cy + dy / view.s
        view.cx = target.cx; view.cy = target.cy
      }
    }
    const k = drag?.moved ? null : hitTest(sx, sy)
    if (k !== hoverKey) { hoverKey = k; cb.onHover?.(k) }
    canvas.style.cursor = drag?.moved ? 'grabbing' : k ? 'pointer' : 'crosshair'
    const [wx, wy] = toWorld(sx, sy)
    cb.onCursor?.({ x: wx, y: wy })
  }
  function onUp(e: PointerEvent) {
    if (drag && !drag.moved) {
      const r = canvas.getBoundingClientRect()
      cb.onSelect?.(hitTest(e.clientX - r.left, e.clientY - r.top))
    }
    drag = null
  }
  function onLeave() { cb.onCursor?.(null); if (hoverKey) { hoverKey = null; cb.onHover?.(null) } }
  function zoomAt(f: number, sx = W / 2, sy = H / 2) {
    const [wx, wy] = toWorld(sx, sy)
    const ns = Math.min(MAX_SCALE, Math.max(MIN_SCALE, target.s * f))
    target.s = ns
    if (!follow) {
      target.cx = wx - (sx - W / 2) / ns
      target.cy = wy + (sy - H / 2) / ns
    }
  }
  function onWheel(e: WheelEvent) {
    e.preventDefault()
    const r = canvas.getBoundingClientRect()
    zoomAt(Math.exp(-e.deltaY * 0.0015), e.clientX - r.left, e.clientY - r.top)
  }
  canvas.addEventListener('pointerdown', onDown)
  canvas.addEventListener('pointermove', onMove)
  canvas.addEventListener('pointerup', onUp)
  canvas.addEventListener('pointerleave', onLeave)
  canvas.addEventListener('wheel', onWheel, { passive: false })

  function ensureChunks(x0: number, x1: number, y0: number, y1: number, budgetMs: number) {
    const t0 = performance.now()
    for (let cy = Math.floor(y0 / CHUNK_M); cy <= Math.floor(y1 / CHUNK_M); cy++) {
      for (let cx = Math.floor(x0 / CHUNK_M); cx <= Math.floor(x1 / CHUNK_M); cx++) {
        const k = cx + ',' + cy
        if (chunks.has(k)) continue
        if (performance.now() - t0 > budgetMs) return
        chunks.set(k, renderTerrainChunk(cx, cy))
        if (chunks.size > MAX_CHUNKS) chunks.delete(chunks.keys().next().value as string)
      }
    }
  }

  // Hidden tabs throttle rAF to zero; fall back to a slow timer so state stays current.
  function schedule() {
    if (destroyed) return
    if (document.hidden) timeout = window.setTimeout(frame, 120)
    else raf = requestAnimationFrame(frame)
  }

  function frame() {
    schedule()
    if (W < 2) return
    const frameTime = performance.now()
    if (frameTime - lastDraw < (reducedMotion ? 100 : 32)) return
    lastDraw = frameTime
    const m = getModel()
    const now = frameTime
    const wall = Date.now()
    const boot = reducedMotion ? 1 : ease((now - bootStart) / 1900)
    const infoAgeMs = m.lastCaptureMs ? Math.max(0, wall - m.lastCaptureMs) : 0
    const live = m.posture === 'NOMINAL' || m.posture === 'DEGRADED' || m.posture === 'RECOVERY'

    // Rover display position eases toward the latest accepted fix. No extrapolation.
    const rv = m.rover
    if (rv) {
      if (!lastRover) lastRover = { x: rv.x, y: rv.y }
      if (rv.seq !== roverAnim?.seq) {
        roverAnim = { seq: rv.seq, fx: lastRover.x, fy: lastRover.y, tx: rv.x, ty: rv.y, t0: now }
        if (rv.seq !== lastPulseSeq) { if (!reducedMotion) pulses.push({ t0: now, late: rv.latencyMs > 2.5 * m.intervalMs }); lastPulseSeq = rv.seq }
      }
      const k = reducedMotion ? 1 : ease((now - roverAnim.t0) / 650)
      lastRover = { x: roverAnim.fx + (roverAnim.tx - roverAnim.fx) * k, y: roverAnim.fy + (roverAnim.ty - roverAnim.fy) * k }
    } else { lastRover = null; roverAnim = null }
    if (follow && lastRover) {
      target.cx = lastRover.x + (W * 0.1) / view.s
      target.cy = lastRover.y
    }
    view.s += (target.s - view.s) * (reducedMotion ? 1 : 0.2)
    view.cx += (target.cx - view.cx) * (reducedMotion ? 1 : 0.14)
    view.cy += (target.cy - view.cy) * (reducedMotion ? 1 : 0.14)

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.fillStyle = '#03070c'
    ctx.fillRect(0, 0, W, H)
    const [wx0, wy1] = toWorld(0, 0)
    const [wx1, wy0] = toWorld(W, H)
    ensureChunks(wx0, wx1, wy0, wy1, boot < 1 ? 14 : 6)

    // terrain
    ctx.save()
    ctx.globalAlpha = 0.92 * boot
    ctx.imageSmoothingEnabled = true
    for (let cy = Math.floor(wy0 / CHUNK_M); cy <= Math.floor(wy1 / CHUNK_M); cy++) {
      for (let cx = Math.floor(wx0 / CHUNK_M); cx <= Math.floor(wx1 / CHUNK_M); cx++) {
        const c = chunks.get(cx + ',' + cy)
        if (!c) continue
        const [sx, sy] = toScreen(cx * CHUNK_M, (cy + 1) * CHUNK_M)
        ctx.drawImage(c, Math.floor(sx), Math.floor(sy), Math.ceil(CHUNK_M * view.s) + 1, Math.ceil(CHUNK_M * view.s) + 1)
      }
    }
    ctx.restore()
    // atmosphere: cool wash, vignette, grain
    const vg = ctx.createRadialGradient(W * 0.5, H * 0.48, Math.min(W, H) * 0.2, W * 0.5, H * 0.5, Math.max(W, H) * 0.75)
    vg.addColorStop(0, 'rgba(3,7,12,0.08)'); vg.addColorStop(1, 'rgba(3,7,12,0.82)')
    ctx.fillStyle = vg; ctx.fillRect(0, 0, W, H)
    ctx.fillStyle = 'rgba(10,32,44,0.18)'; ctx.fillRect(0, 0, W, H)
    if (!grain) grain = makeGrain()
    if (grain) { ctx.save(); ctx.globalAlpha = 0.05; ctx.globalCompositeOperation = 'screen'; ctx.fillStyle = grain; ctx.fillRect(0, 0, W, H); ctx.restore() }

    // boot reveal: grows from the rover (or center)
    ctx.save()
    const [ox, oy] = lastRover ? toScreen(lastRover.x, lastRover.y) : [W / 2, H / 2]
    if (boot < 1) { ctx.beginPath(); ctx.arc(ox, oy, boot * Math.hypot(W, H), 0, Math.PI * 2); ctx.clip() }

    // grid
    const minor = niceStep(16 / view.s)
    const major = minor * (minor === 2 || minor === 20 ? 5 : minor === 0.25 ? 4 : minor === 0.5 ? 2 : 5)
    ctx.lineWidth = 1
    for (let pass = 0; pass < 2; pass++) {
      const st = pass ? major : minor
      ctx.strokeStyle = pass ? 'rgba(159,204,220,0.17)' : 'rgba(159,204,220,0.055)'
      ctx.beginPath()
      for (let x = Math.ceil(wx0 / st) * st; x <= wx1; x += st) { const sx = Math.round(toScreen(x, 0)[0]) + 0.5; ctx.moveTo(sx, 0); ctx.lineTo(sx, H) }
      for (let y = Math.ceil(wy0 / st) * st; y <= wy1; y += st) { const sy = Math.round(toScreen(0, y)[1]) + 0.5; ctx.moveTo(0, sy); ctx.lineTo(W, sy) }
      ctx.stroke()
    }
    // axis labels
    ctx.font = `500 10px ${MONO}`
    ctx.fillStyle = 'rgba(3,7,12,0.55)'; ctx.fillRect(0, 0, W, 20); ctx.fillRect(0, 20, 46, H - 20)
    ctx.fillStyle = 'rgba(165,185,196,0.85)'
    ctx.textBaseline = 'middle'
    for (let x = Math.ceil(wx0 / major) * major; x <= wx1; x += major) {
      const sx = toScreen(x, 0)[0]; if (sx < 60) continue
      ctx.textAlign = 'center'; ctx.fillText(fmt(+x.toFixed(2)), sx, 10)
    }
    for (let y = Math.ceil(wy0 / major) * major; y <= wy1; y += major) {
      const sy = toScreen(0, y)[1]; if (sy < 30 || sy > H - 10) continue
      ctx.textAlign = 'left'; ctx.fillText(fmt(+y.toFixed(2)), 6, sy)
    }
    ctx.fillStyle = 'rgba(155,221,234,0.95)'
    ctx.textAlign = 'left'; ctx.fillText('E m →', 52, 10)
    ctx.save(); ctx.translate(14, H - 54); ctx.rotate(-Math.PI / 2); ctx.fillText('N m →', 0, 0); ctx.restore()

    // origin / mission start marker
    {
      const [sx, sy] = toScreen(0, 0)
      ctx.strokeStyle = 'rgba(194,220,227,0.7)'; ctx.lineWidth = 1
      ctx.beginPath(); ctx.moveTo(sx - 9, sy); ctx.lineTo(sx + 9, sy); ctx.moveTo(sx, sy - 9); ctx.lineTo(sx, sy + 9); ctx.stroke()
      ctx.beginPath(); ctx.arc(sx, sy, 4, 0, Math.PI * 2); ctx.stroke()
      ctx.fillStyle = 'rgba(194,220,227,0.75)'; ctx.font = `500 9px ${MONO}`; ctx.textAlign = 'left'
      ctx.fillText('ORIGIN · START MARKER', sx + 10, sy + 12)
    }

    const tSel = m.selectedKey
    // range rings around the last known rover position
    if (m.layers.rings && lastRover) {
      const [sx, sy] = toScreen(lastRover.x, lastRover.y)
      ctx.setLineDash([2, 5]); ctx.lineWidth = 1
      for (const r of [5, 10, 20]) {
        const pr = r * view.s
        if (pr < 30 || pr > Math.hypot(W, H)) continue
        ctx.strokeStyle = 'rgba(155,221,234,0.16)'
        ctx.beginPath(); ctx.arc(sx, sy, pr, 0, Math.PI * 2); ctx.stroke()
        ctx.fillStyle = 'rgba(155,221,234,0.55)'; ctx.font = `500 9px ${MONO}`; ctx.textAlign = 'left'
        ctx.fillText(r + ' m', sx + pr * 0.7071 + 4, sy - pr * 0.7071 - 4)
      }
      ctx.setLineDash([])
    }

    // trail of accepted fixes; dashed amber where sequence numbers were skipped (path unobserved)
    if (m.layers.trail && m.trail.length) {
      const n = m.trail.length
      ctx.lineCap = 'round'
      for (let i = 1; i < n; i++) {
        const a = m.trail[i - 1], b = m.trail[i]
        const last = i === n - 1
        const [ax, ay] = toScreen(a.x, a.y)
        const [bx, by] = last && lastRover ? toScreen(lastRover.x, lastRover.y) : toScreen(b.x, b.y)
        const age = (n - i) / n
        if (b.gap > 0) { ctx.setLineDash([3, 4]); ctx.strokeStyle = `rgba(${AMBER},${0.55 - age * 0.25})`; ctx.lineWidth = 1.2 }
        else { ctx.setLineDash([]); ctx.strokeStyle = `rgba(${CYAN},${0.85 - age * 0.6})`; ctx.lineWidth = 2 }
        ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.stroke()
      }
      ctx.setLineDash([])
      for (let i = 0; i < n - 1; i++) {
        const p = m.trail[i]; const [x, y] = toScreen(p.x, p.y)
        ctx.fillStyle = `rgba(${CYAN},${0.25 + (i / n) * 0.5})`
        ctx.fillRect(x - 1.5, y - 1.5, 3, 3)
      }
    }

    // hazards
    const hz = m.hazards.filter((h) => m.filters[h.type] && h.confidence >= m.minConfidence)
    for (const h of hz) {
      const st = HAZARD_STYLE[h.type]
      const [sx, sy] = toScreen(h.x, h.y)
      if (sx < -80 || sy < -80 || sx > W + 80 || sy > H + 80) continue
      const sel = h.key === tSel, hov = h.key === hoverKey
      const aged = h.ageMs > m.agedHazardMs
      const alpha = aged && !sel ? 0.55 : 1
      if (m.layers.unc && h.unc > 0) {
        const pr = h.unc * view.s
        ctx.fillStyle = `rgba(${st.rgb},${(sel ? 0.16 : 0.08) * alpha})`
        ctx.beginPath(); ctx.arc(sx, sy, pr, 0, Math.PI * 2); ctx.fill()
        ctx.setLineDash([3, 3]); ctx.strokeStyle = `rgba(${st.rgb},${0.55 * alpha})`; ctx.lineWidth = 1
        ctx.stroke(); ctx.setLineDash([])
      }
      const fresh = wall - h.firstRxMs
      if (!reducedMotion && fresh < 2200) {
        const k = fresh / 2200
        ctx.strokeStyle = `rgba(${st.rgb},${(1 - k) * 0.9})`; ctx.lineWidth = 1.5
        ctx.beginPath(); ctx.arc(sx, sy, 8 + k * 46, 0, Math.PI * 2); ctx.stroke()
      }
      ctx.lineWidth = 1.5
      ctx.globalAlpha = alpha
      ctx.fillStyle = 'rgba(3,7,12,0.7)'; ctx.beginPath(); ctx.arc(sx, sy, 9, 0, Math.PI * 2); ctx.fill()
      glyph(ctx, h.type, sx, sy, sel || hov ? 5.5 : 4.5, st.color, h.type !== 'crater')
      // confidence ring: arc length = confidence
      ctx.strokeStyle = `rgba(${st.rgb},0.25)`; ctx.lineWidth = 2
      ctx.beginPath(); ctx.arc(sx, sy, 11, 0, Math.PI * 2); ctx.stroke()
      ctx.strokeStyle = st.color
      ctx.beginPath(); ctx.arc(sx, sy, 11, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * h.confidence); ctx.stroke()
      ctx.globalAlpha = 1
      if (view.s > 26 || sel || hov) {
        ctx.font = `500 10px ${MONO}`; ctx.textAlign = 'left'; ctx.textBaseline = 'middle'
        const label = h.id.toUpperCase()
        const tw = ctx.measureText(label).width
        ctx.fillStyle = 'rgba(3,7,12,0.72)'; ctx.fillRect(sx + 16, sy - 8, tw + 10, 16)
        ctx.fillStyle = sel || hov ? '#eafaff' : `rgba(220,232,236,${0.8 * alpha})`
        ctx.fillText(label, sx + 21, sy)
      }
      if (sel) {
        const t = (now / 1000) % 1
        const r = 18 + Math.sin(t * Math.PI * 2) * 1.5
        ctx.strokeStyle = '#eafaff'; ctx.lineWidth = 1.5
        for (let q = 0; q < 4; q++) {
          const a = (q * Math.PI) / 2 + Math.PI / 4
          const cx = sx + Math.cos(a) * r, cy = sy + Math.sin(a) * r
          const dx = Math.cos(a) > 0 ? -1 : 1, dy = Math.sin(a) > 0 ? -1 : 1
          ctx.beginPath(); ctx.moveTo(cx + dx * 7, cy); ctx.lineTo(cx, cy); ctx.lineTo(cx, cy + dy * 7); ctx.stroke()
        }
        if (lastRover && rv) {
          const [rx, ry] = toScreen(lastRover.x, lastRover.y)
          ctx.setLineDash([4, 4]); ctx.strokeStyle = 'rgba(234,250,255,0.55)'; ctx.lineWidth = 1
          ctx.beginPath(); ctx.moveTo(rx, ry); ctx.lineTo(sx, sy); ctx.stroke(); ctx.setLineDash([])
          const dist = Math.hypot(h.x - rv.x, h.y - rv.y)
          const mx = (rx + sx) / 2, my = (ry + sy) / 2
          const label = dist.toFixed(2) + ' m'
          ctx.font = `500 10px ${MONO}`; const tw = ctx.measureText(label).width
          ctx.fillStyle = 'rgba(3,7,12,0.85)'; ctx.fillRect(mx - tw / 2 - 5, my - 8, tw + 10, 16)
          ctx.fillStyle = '#eafaff'; ctx.textAlign = 'center'; ctx.fillText(label, mx, my)
        }
      }
    }

    // rover
    if (rv && lastRover) {
      const [sx, sy] = toScreen(lastRover.x, lastRover.y)
      const stale = !live
      // Possible-travel envelope (INFERRED): max observed speed × information age.
      if (stale && m.layers.envelope && m.maxSpeed > 0) {
        const rM = Math.min(60, m.maxSpeed * (infoAgeMs / 1000))
        const pr = rM * view.s
        ctx.fillStyle = `rgba(${AMBER},0.05)`
        ctx.beginPath(); ctx.arc(sx, sy, pr, 0, Math.PI * 2); ctx.fill()
        ctx.setLineDash([6, 5]); ctx.lineDashOffset = -now / 60
        ctx.strokeStyle = `rgba(${AMBER},0.7)`; ctx.lineWidth = 1.2; ctx.stroke(); ctx.setLineDash([]); ctx.lineDashOffset = 0
        ctx.font = `500 10px ${MONO}`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'
        const lab = `POSSIBLE TRAVEL ≤ ${rM.toFixed(1)} m · INFERRED`
        const tw = ctx.measureText(lab).width
        const ly = sy - pr - 12
        ctx.fillStyle = 'rgba(3,7,12,0.8)'; ctx.fillRect(sx - tw / 2 - 6, ly - 8, tw + 12, 16)
        ctx.fillStyle = `rgba(${AMBER},1)`; ctx.fillText(lab, sx, ly)
      }
      // reception pulses: one per accepted frame (amber if the frame was late)
      for (let i = pulses.length - 1; i >= 0; i--) {
        const p = pulses[i]; const k = (now - p.t0) / 1300
        if (k > 1) { pulses.splice(i, 1); continue }
        ctx.strokeStyle = `rgba(${p.late ? AMBER : CYAN},${(1 - k) * 0.7})`; ctx.lineWidth = 1.2
        ctx.beginPath(); ctx.arc(sx, sy, 10 + ease(k) * 38, 0, Math.PI * 2); ctx.stroke()
      }
      // position uncertainty (to scale)
      const ur = Math.max(rv.unc * view.s, 0)
      ctx.fillStyle = stale ? 'rgba(194,220,227,0.06)' : `rgba(${CYAN},0.12)`
      ctx.beginPath(); ctx.arc(sx, sy, ur, 0, Math.PI * 2); ctx.fill()
      ctx.strokeStyle = stale ? 'rgba(194,220,227,0.35)' : `rgba(${CYAN},0.5)`; ctx.lineWidth = 1; ctx.stroke()
      // course over ground (derived from consecutive accepted fixes; the contract has no heading)
      if (rv.cog != null && m.layers.cog) {
        const ux = Math.sin(rv.cog), uy = -Math.cos(rv.cog)
        ctx.strokeStyle = stale ? 'rgba(194,220,227,0.5)' : `rgba(${CYAN},0.9)`; ctx.lineWidth = 1.5
        ctx.beginPath(); ctx.moveTo(sx + ux * 13, sy + uy * 13); ctx.lineTo(sx + ux * 30, sy + uy * 30); ctx.stroke()
        const tx = sx + ux * 30, ty = sy + uy * 30
        ctx.beginPath(); ctx.moveTo(tx, ty); ctx.lineTo(tx - ux * 6 + uy * 4, ty - uy * 6 - ux * 4); ctx.moveTo(tx, ty); ctx.lineTo(tx - ux * 6 - uy * 4, ty - uy * 6 + ux * 4); ctx.stroke()
      }
      // marker
      ctx.fillStyle = 'rgba(3,7,12,0.85)'
      ctx.beginPath(); ctx.arc(sx, sy, 10, 0, Math.PI * 2); ctx.fill()
      ctx.lineWidth = 1.5
      ctx.strokeStyle = stale ? '#c2dce3' : '#9bddea'
      ctx.beginPath(); ctx.arc(sx, sy, 10, 0, Math.PI * 2); ctx.stroke()
      ctx.save(); ctx.translate(sx, sy); ctx.rotate(Math.PI / 4)
      if (stale) { ctx.strokeStyle = '#c2dce3'; ctx.strokeRect(-3.5, -3.5, 7, 7) }
      else { ctx.fillStyle = '#c9f3fa'; ctx.shadowColor = '#9bddea'; ctx.shadowBlur = 12; ctx.fillRect(-3.5, -3.5, 7, 7) }
      ctx.restore()
      if (stale) {
        // information-age dial (full circle = 30 s)
        const k = Math.min(1, infoAgeMs / 30000)
        ctx.strokeStyle = `rgba(${m.posture === 'BLACKOUT' ? RED : AMBER},0.95)`; ctx.lineWidth = 2
        ctx.beginPath(); ctx.arc(sx, sy, 15, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * k); ctx.stroke()
      }
      ctx.font = `600 10px ${MONO}`; ctx.textAlign = 'left'; ctx.textBaseline = 'middle'
      const tag = stale ? `LAST KNOWN · ${(infoAgeMs / 1000).toFixed(1)} s` : rv.roverId.toUpperCase()
      const tw = ctx.measureText(tag).width
      ctx.fillStyle = 'rgba(3,7,12,0.82)'; ctx.fillRect(sx + 20, sy + 10, tw + 12, 17)
      ctx.fillStyle = stale ? `rgba(${m.posture === 'BLACKOUT' ? RED : AMBER},1)` : '#c9f3fa'
      ctx.fillText(tag, sx + 26, sy + 18.5)
    }
    ctx.restore() // boot clip

    // boot scan line
    if (boot < 1) {
      const y = H * ease((now - bootStart) / 1500)
      const g = ctx.createLinearGradient(0, y - 60, 0, y)
      g.addColorStop(0, `rgba(${CYAN},0)`); g.addColorStop(1, `rgba(${CYAN},0.12)`)
      ctx.fillStyle = g; ctx.fillRect(0, y - 60, W, 60)
      ctx.fillStyle = `rgba(${CYAN},0.6)`; ctx.fillRect(0, y, W, 1)
    }

    // reception wavefront (once, when station transport reconnects)
    if (!reducedMotion && m.recoveryStartMs && lastRover) {
      const k = (wall - m.recoveryStartMs) / 2400
      if (k >= 0 && k < 1) {
        const [sx, sy] = toScreen(lastRover.x, lastRover.y)
        const r = ease(k) * Math.hypot(W, H)
        ctx.strokeStyle = `rgba(${CYAN},${(1 - k) * 0.8})`; ctx.lineWidth = 2
        ctx.beginPath(); ctx.arc(sx, sy, r, 0, Math.PI * 2); ctx.stroke()
        ctx.strokeStyle = `rgba(${CYAN},${(1 - k) * 0.25})`; ctx.lineWidth = 14
        ctx.beginPath(); ctx.arc(sx, sy, Math.max(0, r - 10), 0, Math.PI * 2); ctx.stroke()
      }
    }

    // interrupted transport or stale telemetry: dimmed, hatched, pulsing edge
    if (m.posture === 'BLACKOUT' || m.posture === 'TRANSPORT_DOWN' || m.posture === 'STALE') {
      const col = m.posture === 'BLACKOUT' || m.posture === 'TRANSPORT_DOWN' ? RED : AMBER
      ctx.fillStyle = 'rgba(3,7,12,0.28)'; ctx.fillRect(0, 0, W, H)
      ctx.save(); ctx.strokeStyle = `rgba(${col},0.045)`; ctx.lineWidth = 1
      ctx.beginPath(); for (let x = -H; x < W; x += 9) { ctx.moveTo(x, H); ctx.lineTo(x + H, 0) } ctx.stroke(); ctx.restore()
      const pulse = 0.5 + 0.5 * Math.sin(now / 420)
      const eg = ctx.createRadialGradient(W / 2, H / 2, Math.min(W, H) * 0.35, W / 2, H / 2, Math.max(W, H) * 0.72)
      eg.addColorStop(0, `rgba(${col},0)`); eg.addColorStop(1, `rgba(${col},${0.12 + pulse * 0.08})`)
      ctx.fillStyle = eg; ctx.fillRect(0, 0, W, H)
    }

    // scale bar + north arrow
    {
      const len = niceStep(120 / view.s)
      const px = len * view.s
      const x = 62, y = H - 22
      ctx.fillStyle = 'rgba(3,7,12,0.7)'; ctx.fillRect(x - 8, y - 18, px + 70, 28)
      ctx.strokeStyle = '#c2dce3'; ctx.lineWidth = 1
      ctx.beginPath(); ctx.moveTo(x, y - 5); ctx.lineTo(x, y); ctx.lineTo(x + px, y); ctx.lineTo(x + px, y - 5); ctx.moveTo(x + px / 2, y); ctx.lineTo(x + px / 2, y - 3); ctx.stroke()
      ctx.fillStyle = '#c2dce3'; ctx.font = `500 10px ${MONO}`; ctx.textAlign = 'left'; ctx.textBaseline = 'middle'
      ctx.fillText(`${len} m`, x + px + 8, y - 2)
      const nx = W - 26, ny = 46
      ctx.strokeStyle = 'rgba(194,220,227,0.8)'
      ctx.beginPath(); ctx.moveTo(nx, ny + 12); ctx.lineTo(nx, ny - 8); ctx.moveTo(nx - 4, ny - 3); ctx.lineTo(nx, ny - 8); ctx.lineTo(nx + 4, ny - 3); ctx.stroke()
      ctx.textAlign = 'center'; ctx.fillText('N', nx, ny - 16)
    }
    cb.onFrame?.({ scale: view.s })
  }
  schedule()

  return {
    setFollow(v) { follow = v; cb.onFollowChange?.(v) },
    reboot() { bootStart = performance.now() },
    zoomBy(f) { zoomAt(f) },
    centerOn(x, y) { setFollow(false); target.cx = x; target.cy = y },
    fit(points) {
      if (!points.length) return
      setFollow(false)
      let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity
      for (const p of points) { x0 = Math.min(x0, p.x); x1 = Math.max(x1, p.x); y0 = Math.min(y0, p.y); y1 = Math.max(y1, p.y) }
      target.cx = (x0 + x1) / 2; target.cy = (y0 + y1) / 2
      target.s = Math.min(MAX_SCALE, Math.max(MIN_SCALE, Math.min((W - 140) / Math.max(4, x1 - x0), (H - 140) / Math.max(4, y1 - y0))))
    },
    destroy() {
      destroyed = true
      cancelAnimationFrame(raf); clearTimeout(timeout); ro.disconnect()
      canvas.removeEventListener('pointerdown', onDown); canvas.removeEventListener('pointermove', onMove)
      canvas.removeEventListener('pointerup', onUp); canvas.removeEventListener('pointerleave', onLeave)
      canvas.removeEventListener('wheel', onWheel)
      chunks.clear()
    },
  }
}
