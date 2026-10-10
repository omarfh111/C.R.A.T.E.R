import type { TelemetryState } from '../../telemetry/state'
import { HAZARD_STYLE, MC_COLORS, THRESHOLDS } from './constants'
import type { CommsDerivation } from './derive'
import { ageStr, bearingDeg, clk, clkS, pad3, sgn } from './format'
import type { Journal } from './journal'
import type { HazardFilters, HazardType, MapHazard, Posture } from './types'

// Pure presenters: TelemetryState + Journal + derivation → display strings/colors. No React, no side effects.

export function postureSubline(d: CommsDerivation, j: Journal, nowMs: number): string {
  const age = d.ageMs != null ? (d.ageMs / 1000).toFixed(1) : '—'
  const lines: Record<Posture, string> = {
    ACQUIRING: 'Waiting for first valid frame',
    NOMINAL: `Frames accepted at cadence · last rx ${age} s`,
    DEGRADED: `Intermittent reception · yield ${d.yield != null ? Math.round(d.yield * 100) + '%' : '—'} · last rx ${age} s`,
    STALE: `Transport up, no accepted frame for ${age} s`,
    BLACKOUT: `Simulated radio blackout ${j.interruptionStartMs != null ? ((nowMs - j.interruptionStartMs) / 1000).toFixed(1) : '—'} s · display frozen at seq ${d.frame?.sequence ?? '—'}`,
    TRANSPORT_DOWN: `Station WebSocket disconnected ${j.interruptionStartMs != null ? ((nowMs - j.interruptionStartMs) / 1000).toFixed(1) : '—'} s · rover radio state unknown`,
    RECOVERY: `Station reception resumed · ${j.recovery?.frames ?? 0} frames reconciled`,
  }
  return lines[d.posture]
}

export type BannerView = { rgb: string; kicker: string; timer: string; title: string; line1: string; line2: string } | null
export function outageBanner(d: CommsDerivation, j: Journal, nowMs: number): BannerView {
  const f = d.frame
  if (d.posture === 'BLACKOUT') {
    return {
      rgb: '239,91,76', kicker: 'MOCK · SIMULATED RADIO BLACKOUT',
      timer: 'T+ ' + (j.interruptionStartMs != null ? ((nowMs - j.interruptionStartMs) / 1000).toFixed(1) : '—') + ' s',
      title: 'Simulated radio blackout',
      line1: `Display frozen at last accepted frame · seq ${f?.sequence ?? '—'} · captured ${f ? clk(Date.parse(f.capturedAt)) : '—'}Z`,
      line2: 'No position or hazard observations are being received. Amber envelope shows inferred maximum travel since last fix.',
    }
  }
  if (d.posture === 'TRANSPORT_DOWN') {
    return {
      rgb: '239,91,76', kicker: 'MISSION CONTROL · STATION TRANSPORT DOWN',
      timer: 'T+ ' + (j.interruptionStartMs != null ? ((nowMs - j.interruptionStartMs) / 1000).toFixed(1) : '—') + ' s',
      title: 'Station connection lost',
      line1: `Last accepted frame · seq ${f?.sequence ?? '—'} · captured ${f ? clk(Date.parse(f.capturedAt)) : '—'}Z`,
      line2: 'The WebSocket is disconnected. Current rover radio state is unknown; displayed observations are from accepted telemetry.',
    }
  }
  if (d.posture === 'STALE' && d.ageMs != null && d.lastRxMs != null) {
    return {
      rgb: '242,181,74', kicker: 'MISSION CONTROL · TRANSPORT UP, SILENT', timer: 'AGE ' + (d.ageMs / 1000).toFixed(1) + ' s',
      title: 'No fresh telemetry', line1: `Last accepted frame seq ${f?.sequence ?? '—'} · received ${clk(d.lastRxMs)}Z`,
      line2: 'Transport reports connected but no valid frame has been accepted within the stale threshold.',
    }
  }
  if (d.posture === 'RECOVERY' && j.recovery) {
    const r = j.recovery
    const pl = (n: number, w: string) => `${n} ${w}${n === 1 ? '' : 's'}`
    return {
      rgb: '155,221,234', kicker: 'MISSION CONTROL · RECEPTION RESUMED', timer: 'INTERRUPTION ' + (r.outageMs / 1000).toFixed(1) + ' s',
      title: 'Telemetry reception resumed',
      line1: `${pl(r.frames, 'frame')} accepted · ${r.delayed} delayed · ${pl(r.gap, 'inferred sequence gap')} · ${pl(r.hazards, 'new hazard')}`,
      line2: r.gap ? 'Sequence gaps indicate frames not accepted by Mission Control. Their observations are not shown.' : 'No sequence numbers skipped across the interruption.',
    }
  }
  return null
}

export function roverView(d: CommsDerivation, j: Journal) {
  const f = d.frame
  if (!f || d.lastRxMs == null) return null
  const capMs = Date.parse(f.capturedAt)
  const lat = d.lastRxMs - capMs
  return {
    id: f.roverId, seq: f.sequence,
    e: sgn(f.roverPosition.xM), n: sgn(f.roverPosition.yM), u: sgn(f.roverPosition.zM),
    unc: '± ' + f.positionUncertaintyRadiusM.toFixed(2) + ' m',
    cog: j.cogRad != null ? pad3(Math.round(((j.cogRad * 180) / Math.PI + 360) % 360)) + '° from fixes' : '—',
    captured: clk(capMs), received: clk(d.lastRxMs),
    latency: (lat / 1000).toFixed(2) + ' s', late: lat > THRESHOLDS.lateIntervals * d.intervalMs,
  }
}

export function ageView(d: CommsDerivation) {
  const a = d.ageMs
  const color = a == null ? MC_COLORS.dim : a > d.staleMs || d.posture === 'BLACKOUT' || d.posture === 'TRANSPORT_DOWN' ? MC_COLORS.red : a > d.degradedMs ? MC_COLORS.amber : MC_COLORS.cyan
  return {
    value: a != null ? (a / 1000).toFixed(1) : '—', color,
    pct: a != null ? Math.min(100, (a / d.staleMs) * 100) : 0,
    degradedPct: (d.degradedMs / d.staleMs) * 100,
    degradedS: (d.degradedMs / 1000).toFixed(0), staleS: (d.staleMs / 1000).toFixed(0),
    state: d.posture === 'BLACKOUT' || d.posture === 'TRANSPORT_DOWN' ? 'LAST KNOWN' : a == null ? 'NO DATA' : a > d.staleMs ? 'STALE' : a > d.degradedMs ? 'AGING' : 'FRESH',
  }
}

export function linkView(tel: TelemetryState, d: CommsDerivation, j: Journal, nowMs: number) {
  const tColor = { connected: MC_COLORS.cyan, connecting: MC_COLORS.steel, disconnected: MC_COLORS.red }[tel.transportStatus]
  const f = d.frame
  const rl = f?.link.status
  return {
    transport: { label: tel.transportStatus.toUpperCase(), color: tColor, since: 'since ' + clkS(j.transportSince) + 'Z' },
    rover: f && rl
      ? { label: rl.toUpperCase(), color: rl === 'connected' ? MC_COLORS.cyan : rl === 'degraded' ? MC_COLORS.amber : MC_COLORS.red, asOf: `as of seq ${f.sequence} · ${ageStr(nowMs - Date.parse(f.capturedAt))} ago` }
      : { label: '—', color: MC_COLORS.dim, asOf: 'no frame yet' },
    mismatch: !!f && tel.transportStatus === 'disconnected' && rl === 'connected',
    yieldText: d.yield != null ? Math.round(d.yield * 100) + '% (derived)' : '—',
  }
}

export function mapHazards(tel: TelemetryState, j: Journal, nowMs: number): MapHazard[] {
  return Object.entries(tel.hazards).map(([key, h]) => {
    const obs = Date.parse(h.observedAt)
    return {
      key, id: h.id, type: h.type, x: h.position.xM, y: h.position.yM, z: h.position.zM,
      unc: h.uncertaintyRadiusM, confidence: h.confidence, observedMs: obs, ageMs: nowMs - obs,
      firstRxMs: j.hazardMeta[key]?.firstRxMs ?? 0,
    }
  })
}

export type SortMode = 'RECENT' | 'NEAREST'
export function sortedInventory(list: MapHazard[], filters: HazardFilters, sort: SortMode, rx: number, ry: number) {
  const inv = list.filter((h) => filters[h.type])
  if (sort === 'NEAREST') inv.sort((a, b) => Math.hypot(a.x - rx, a.y - ry) - Math.hypot(b.x - rx, b.y - ry))
  else inv.sort((a, b) => b.observedMs - a.observedMs || b.firstRxMs - a.firstRxMs)
  return inv
}

export function typeCounts(list: MapHazard[]): Record<HazardType, number> {
  const c: Record<HazardType, number> = { crater: 0, rock: 0, slope: 0, unknown: 0 }
  for (const h of list) c[h.type]++
  return c
}

export function inspectorView(h: MapHazard, j: Journal, d: CommsDerivation, agedMs: number) {
  const st = HAZARD_STYLE[h.type]
  const meta = j.hazardMeta[h.key]
  const f = d.frame
  const rx = f?.roverPosition.xM ?? 0, ry = f?.roverPosition.yM ?? 0
  const dx = h.x - rx, dy = h.y - ry
  const aged = h.ageMs > agedMs
  return {
    id: h.id, type: h.type, typeLabel: st.label + ' · OBSERVED HAZARD', color: st.color, rgb: st.rgb, aged,
    conf: h.confidence.toFixed(2) + ' / 1.00', confPct: h.confidence * 100,
    pos: `${sgn(h.x)}  ${sgn(h.y)}  ${sgn(h.z)}`, unc: '± ' + h.unc.toFixed(2) + ' m radius',
    observed: clk(h.observedMs) + 'Z', age: ageStr(h.ageMs), ageColor: aged ? MC_COLORS.amber : MC_COLORS.text,
    range: f ? `${Math.hypot(dx, dy).toFixed(2)} m · ${pad3(bearingDeg(dx, dy))}°` : '—',
    first: meta ? `seq ${meta.firstSeq} · ${clk(meta.firstRxMs)}` : '—',
    count: String(meta?.count ?? 1),
  }
}

export function demoTickLabel(j: Journal, nowMs: number, cfg: { intervalMs: number; blackoutStartTick: number; blackoutDurationTicks: number }) {
  const tick = Math.floor((nowMs - j.sessionStartMs) / cfg.intervalMs)
  const bo = cfg.blackoutDurationTicks > 0
    ? tick < cfg.blackoutStartTick ? ` · blackout in ${cfg.blackoutStartTick - tick}` : tick < cfg.blackoutStartTick + cfg.blackoutDurationTicks ? ' · in blackout' : ''
    : ''
  return `tick ${tick}${bo}`
}
