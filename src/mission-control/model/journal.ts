import { telemetryFrameSchema, type TelemetryFrame } from '../../telemetry/contract'
import type { AdapterEvent } from '../../telemetry/adapter'
import type { TelemetryState } from '../../telemetry/state'
import { THRESHOLDS } from './constants'
import { sgn } from './format'
import type { EventKind, EventLevel, HazardMeta, JournalEvent, OutageSpan, PacketMark, RecoveryStats, TrailPoint } from './types'

/**
 * Mission Control journal: history the reducer intentionally does not keep (trail, packet marks,
 * outage spans, event log, recovery tally). It is derived ONLY by comparing the reducer's state
 * before and after each adapter event — it never re-validates, re-orders or invents data.
 * The existing `ingestTelemetry` reducer remains the single source of accepted state.
 */
export type Journal = {
  sourceLabel: string
  sessionStartMs: number
  transportSince: number
  everConnected: boolean
  interruptionStartMs: number | null
  recoveryStartMs: number | null
  recovery: RecoveryStats | null
  trail: TrailPoint[]
  packets: PacketMark[]
  spans: OutageSpan[]
  hazardMeta: Record<string, HazardMeta>
  events: JournalEvent[]
  nextEventId: number
  /** Largest speed between consecutive accepted fixes (m/s). Used only for the labelled travel envelope. */
  maxSpeedMps: number
  /** Course over ground from the last two accepted fixes that moved > 5 cm (radians clockwise from north). */
  cogRad: number | null
}

const MAX_TRAIL = 3000
const MAX_EVENTS = 400
const PACKET_WINDOW_MS = 65000

export function createJournal(nowMs: number, sourceLabel: string, detail?: string): Journal {
  const j: Journal = {
    sourceLabel, sessionStartMs: nowMs, transportSince: nowMs, everConnected: false,
    interruptionStartMs: null, recoveryStartMs: null, recovery: null,
    trail: [], packets: [], spans: [], hazardMeta: {}, events: [], nextEventId: 0,
    maxSpeedMps: 0, cogRad: null,
  }
  log(j, nowMs, 'info', 'SESSION', `${sourceLabel} adapter started${detail ? ` · ${detail}` : ''}`)
  return j
}

function log(j: Journal, t: number, level: EventLevel, tag: string, msg: string, kind?: EventKind) {
  j.events.unshift({ id: ++j.nextEventId, t, level, tag, msg, kind: kind ?? level })
  if (j.events.length > MAX_EVENTS) j.events.length = MAX_EVENTS
}

function readFrame(raw: unknown): TelemetryFrame | null {
  try {
    const value = typeof raw === 'string' ? JSON.parse(raw) : raw
    const parsed = telemetryFrameSchema.safeParse(value)
    return parsed.success ? parsed.data : null
  } catch { return null }
}

/**
 * Record one adapter event. Call with the reducer state before and after `ingestTelemetry`.
 * `nowMs` is Mission Control's clock; `intervalMs` is the expected frame cadence (mock config or estimate).
 */
export function recordEvent(j: Journal, prev: TelemetryState, next: TelemetryState, event: AdapterEvent, nowMs: number, intervalMs: number) {
  if (event.type === 'status') {
    if (event.status === prev.transportStatus) return
    j.transportSince = nowMs
    if (event.status === 'connecting') log(j, nowMs, 'info', 'TRANSPORT', 'Opening telemetry source')
    if (event.status === 'disconnected') {
      j.spans.push({ from: nowMs, to: null })
      if (j.everConnected) {
        j.interruptionStartMs = nowMs
        j.recoveryStartMs = null
        log(j, nowMs, 'crit', j.sourceLabel === 'MOCK' ? 'MOCK BLACKOUT' : 'STATION DOWN', `${j.sourceLabel === 'MOCK' ? 'Mock radio blackout' : 'Station WebSocket disconnected; radio state unknown'}. Last accepted seq ${next.latest?.frame.sequence ?? '—'}.`)
      } else log(j, nowMs, 'crit', 'TRANSPORT', 'Source unavailable')
    }
    if (event.status === 'connected') {
      const open = j.spans[j.spans.length - 1]
      if (open && open.to == null) open.to = nowMs
      if (j.everConnected && j.interruptionStartMs != null) {
        j.recoveryStartMs = nowMs
        j.recovery = { outageMs: nowMs - j.interruptionStartMs, frames: 0, delayed: 0, gap: 0, hazards: 0 }
        log(j, nowMs, 'ok', 'TRANSPORT UP', `${j.sourceLabel === 'MOCK' ? 'Mock source' : 'Station WebSocket'} reconnected after ${((nowMs - j.interruptionStartMs) / 1000).toFixed(1)} s. Awaiting fresh frames.`)
      } else log(j, nowMs, 'ok', 'TRANSPORT', `Connected · ${j.sourceLabel} source emitting canonical v1 frames`)
      j.everConnected = true
    }
    return
  }

  const rxMs = Date.parse(event.receivedAt)
  let kind: PacketMark['kind'] = 'accepted'
  let gap = 0
  let late = false
  if (next.invalid > prev.invalid) {
    kind = 'invalid'
    log(j, nowMs, 'warn', 'INVALID', 'Frame failed v1 validation. Counted, not applied.')
  } else if (next.duplicates > prev.duplicates) {
    kind = 'duplicate'
    log(j, nowMs, 'dim', 'DUPLICATE', `seq ${readFrame(event.raw)?.sequence ?? '?'} already accepted · ignored`, 'packet')
  } else if (next.outOfOrder > prev.outOfOrder) {
    kind = 'older'
    const raw = readFrame(event.raw)
    const hz = raw?.hazards.length ?? 0
    const lastSeq = raw ? prev.lastSequenceByRover[raw.roverId] : undefined
    log(j, nowMs, 'warn', 'OUT-OF-ORDER', `seq ${raw?.sequence ?? '?'} arrived after seq ${lastSeq ?? '?'} · discarded${hz ? ` with ${hz} hazard observation${hz > 1 ? 's' : ''}` : ''}`, 'packet')
  } else if (next.accepted > prev.accepted && next.latest) {
    const f = next.latest.frame
    gap = next.sequenceGaps - prev.sequenceGaps
    const capMs = Date.parse(f.capturedAt)
    const latency = rxMs - capMs
    late = latency > THRESHOLDS.lateIntervals * intervalMs
    const p: TrailPoint = { x: f.roverPosition.xM, y: f.roverPosition.yM, seq: f.sequence, gap, t: capMs }
    const last = j.trail[j.trail.length - 1]
    if (last) {
      const d = Math.hypot(p.x - last.x, p.y - last.y)
      const dt = (capMs - last.t) / 1000
      if (dt > 0) j.maxSpeedMps = Math.max(j.maxSpeedMps, d / dt)
      if (d > 0.05) j.cogRad = Math.atan2(p.x - last.x, p.y - last.y)
    }
    j.trail.push(p)
    if (j.trail.length > MAX_TRAIL) j.trail.shift()
    if (gap > 0) log(j, nowMs, 'warn', 'SEQ GAP', `${gap} inferred sequence gap${gap > 1 ? 's' : ''} (${f.sequence - gap}–${f.sequence - 1}). Path between accepted fixes unobserved.`, 'packet')
    if (late) log(j, nowMs, 'warn', 'DELAYED', `seq ${f.sequence} captured ${(latency / 1000).toFixed(1)} s before receipt · applied in order`, 'packet')
    let newHazards = 0
    for (const h of f.hazards) {
      const key = `${f.roverId}:${h.id}`
      const meta = j.hazardMeta[key]
      if (!prev.hazards[key]) {
        newHazards++
        j.hazardMeta[key] = { firstRxMs: rxMs, firstSeq: f.sequence, count: 1 }
        log(j, nowMs, 'haz', 'HAZARD', `${h.id} · ${h.type} at E ${sgn(h.position.xM)} N ${sgn(h.position.yM)} ±${h.uncertaintyRadiusM.toFixed(2)} m · conf ${h.confidence.toFixed(2)}`, 'hazard')
      } else if (meta) { meta.count++; meta.lastSeq = f.sequence }
    }
    log(j, nowMs, 'dim', 'FRAME', `seq ${f.sequence} accepted · E ${sgn(f.roverPosition.xM)} N ${sgn(f.roverPosition.yM)} · rx−cap ${(latency / 1000).toFixed(1)} s`, 'frame')
    if (j.recovery && j.recoveryStartMs != null && rxMs - j.recoveryStartMs < THRESHOLDS.recoveryMs) {
      j.recovery.frames++
      if (late) j.recovery.delayed++
      j.recovery.gap += gap
      j.recovery.hazards += newHazards
    }
  }
  j.packets.push({ t: rxMs, kind, gap, late })
  while (j.packets.length && j.packets[0].t < nowMs - PACKET_WINDOW_MS) j.packets.shift()
}
