import type { OutageSpan, PacketMark } from '../model/types'

/** Reception strip: one mark per packet event (by MC receipt time) over a sliding window; outage spans hatched red. */
export function drawReceptionStrip(canvas: HTMLCanvasElement, packets: PacketMark[], spans: OutageSpan[], nowMs: number, windowMs = 60000) {
  const r = canvas.getBoundingClientRect()
  const dpr = Math.min(2, window.devicePixelRatio || 1)
  const W = Math.max(1, r.width), H = Math.max(1, r.height)
  if (canvas.width !== Math.round(W * dpr)) { canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr) }
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, W, H)
  const X = (t: number) => W - ((nowMs - t) / windowMs) * W
  const base = Math.round(H * 0.62) + 0.5
  for (const s of spans) {
    const x0 = Math.max(0, X(s.from)), x1 = X(s.to ?? nowMs)
    if (x1 < 0) continue
    ctx.fillStyle = 'rgba(239,91,76,0.14)'; ctx.fillRect(x0, 0, x1 - x0, H)
    ctx.strokeStyle = 'rgba(239,91,76,0.35)'; ctx.lineWidth = 1
    ctx.save(); ctx.beginPath(); ctx.rect(x0, 0, x1 - x0, H); ctx.clip()
    ctx.beginPath(); for (let x = x0 - H; x < x1; x += 5) { ctx.moveTo(x, H); ctx.lineTo(x + H, 0) } ctx.stroke(); ctx.restore()
  }
  ctx.strokeStyle = 'rgba(145,214,229,0.2)'; ctx.beginPath(); ctx.moveTo(0, base); ctx.lineTo(W, base); ctx.stroke()
  for (let s = 10000; s < windowMs; s += 10000) {
    const x = Math.round(X(nowMs - s)) + 0.5
    ctx.strokeStyle = 'rgba(145,214,229,0.08)'; ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke()
  }
  for (const p of packets) {
    const x = X(p.t)
    if (x < -2) continue
    const xx = Math.round(x)
    if (p.kind === 'accepted') {
      ctx.fillStyle = p.late ? '#f2b54a' : '#9bddea'; ctx.fillRect(xx - 1, 4, 2, base - 4)
      if (p.gap > 0) { ctx.fillStyle = '#f2b54a'; for (let g = 0; g < Math.min(p.gap, 6); g++) ctx.fillRect(xx - 4 - g * 3, 2, 2, 2) }
    } else {
      ctx.fillStyle = p.kind === 'invalid' ? '#ef5b4c' : p.kind === 'duplicate' ? '#a5b9c4' : '#f2b54a'
      ctx.fillRect(xx - 1, base + 2, 2, H - base - 4)
    }
  }
  ctx.fillStyle = 'rgba(234,250,255,0.9)'; ctx.fillRect(W - 1, 0, 1, H)
}
