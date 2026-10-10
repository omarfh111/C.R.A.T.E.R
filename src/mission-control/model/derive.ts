import type { TelemetryFrame } from '../../telemetry/contract'
import type { TelemetryState } from '../../telemetry/state'
import { THRESHOLDS } from './constants'
import type { Journal } from './journal'
import type { Posture, TrailPoint } from './types'

/**
 * Expected frame cadence. MOCK passes its configured interval. LIVE has no configured cadence,
 * so it is estimated as the median (Δcapture / Δsequence) across recent accepted fixes.
 */
export function estimateIntervalMs(trail: TrailPoint[], fallback = 1000): number {
  const r = trail.slice(-11)
  const steps: number[] = []
  for (let i = 1; i < r.length; i++) {
    const ds = r[i].seq - r[i - 1].seq
    const dt = r[i].t - r[i - 1].t
    if (ds > 0 && dt > 0) steps.push(dt / ds)
  }
  if (!steps.length) return fallback
  steps.sort((a, b) => a - b)
  return steps[Math.floor(steps.length / 2)]
}

/** Accepted ÷ sequence span over the last N accepted frames (Mission Control inference). */
export function frameYield(trail: TrailPoint[]): number | null {
  const recent = trail.slice(-THRESHOLDS.yieldWindow)
  if (recent.length < 5) return null
  return recent.length / (recent[recent.length - 1].seq - recent[0].seq + 1)
}

export type CommsDerivation = {
  frame: TelemetryFrame | undefined
  lastRxMs: number | null
  lastCaptureMs: number | null
  receiptAgeMs: number | null
  ageMs: number | null
  intervalMs: number
  staleMs: number
  degradedMs: number
  yield: number | null
  posture: Posture
}

/**
 * Communications posture as assessed by Mission Control.
 *   ACQUIRING  transport connecting, or connected with no accepted frame yet
 *   BLACKOUT   known MOCK radio simulation interruption
 *   TRANSPORT_DOWN   LIVE station WebSocket disconnected (radio state unknown)
 *   STALE      transport connected, information age > staleMs
 *   RECOVERY   within recoveryMs of transport reconnecting after an interruption
 *   DEGRADED   information age > degradedIntervals × interval, or frame yield < minYield
 *   NOMINAL    otherwise
 */
export function deriveComms(tel: TelemetryState, j: Journal, nowMs: number, intervalMs: number, staleMs: number = THRESHOLDS.staleMs): CommsDerivation {
  const frame = tel.latest?.frame
  const lastRxMs = tel.latest ? Date.parse(tel.latest.receivedAt) : null
  const lastCaptureMs = frame ? Date.parse(frame.capturedAt) : null
  const receiptAgeMs = lastRxMs != null ? Math.max(0, nowMs - lastRxMs) : null
  // A delayed delivery cannot make an old rover fix current again.
  const ageMs = lastCaptureMs != null ? Math.max(0, nowMs - lastCaptureMs) : null
  const degradedMs = THRESHOLDS.degradedIntervals * intervalMs
  const y = frameYield(j.trail)
  let posture: Posture = 'ACQUIRING'
  if (tel.transportStatus === 'disconnected') posture = j.sourceLabel === 'MOCK' && j.everConnected ? 'BLACKOUT' : 'TRANSPORT_DOWN'
  else if (tel.transportStatus === 'connected') {
    if (ageMs != null && ageMs > staleMs) posture = 'STALE'
    else if (j.recoveryStartMs != null && nowMs - j.recoveryStartMs < THRESHOLDS.recoveryMs) posture = 'RECOVERY'
    else if ((ageMs != null && ageMs > degradedMs) || (y != null && y < THRESHOLDS.minYield)) posture = 'DEGRADED'
    else if (frame) posture = 'NOMINAL'
  }
  return { frame, lastRxMs, lastCaptureMs, receiptAgeMs, ageMs, intervalMs, staleMs, degradedMs, yield: y, posture }
}
