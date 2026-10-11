import type { Hazard } from '../../telemetry/contract'

export type HazardType = Hazard['type']
export type Posture = 'ACQUIRING' | 'NOMINAL' | 'DEGRADED' | 'STALE' | 'BLACKOUT' | 'TRANSPORT_DOWN' | 'RECOVERY'
export type EventLevel = 'crit' | 'warn' | 'ok' | 'haz' | 'info' | 'dim'
export type EventKind = 'frame' | 'packet' | 'hazard' | EventLevel
export type PacketKind = 'accepted' | 'invalid' | 'duplicate' | 'older'

/** One accepted rover fix. `gap` = sequence numbers skipped immediately before this fix. */
export type TrailPoint = { x: number; y: number; seq: number; gap: number; t: number }
/** One packet as classified by the existing reducer, keyed by Mission Control receipt time. */
export type PacketMark = { t: number; kind: PacketKind; gap: number; late: boolean }
/** Period during which the MC transport reported `disconnected`. */
export type OutageSpan = { from: number; to: number | null }
export type HazardMeta = { firstRxMs: number; firstSeq: number; count: number; lastSeq?: number }
export type RecoveryStats = { outageMs: number; frames: number; delayed: number; gap: number; hazards: number }
export type JournalEvent = { id: number; t: number; level: EventLevel; tag: string; msg: string; kind: EventKind }

export type MapLayers = { trail: boolean; unc: boolean; rings: boolean; envelope: boolean; cog: boolean }
export type HazardFilters = Record<HazardType, boolean>

export type MapHazard = {
  key: string; id: string; type: HazardType
  x: number; y: number; z: number; unc: number; confidence: number
  observedMs: number; ageMs: number; firstRxMs: number
}
export type MapViewport = { minX: number; maxX: number; minY: number; maxY: number }
export type MapRover = { x: number; y: number; unc: number; seq: number; roverId: string; cog: number | null; latencyMs: number }

/** Everything the canvas renderer reads each animation frame. Built from TelemetryState + Journal. */
export type MapModel = {
  trail: TrailPoint[]
  hazards: MapHazard[]
  rover: MapRover | null
  selectedKey: string | null
  posture: Posture
  lastCaptureMs: number | null
  maxSpeed: number
  layers: MapLayers
  filters: HazardFilters
  minConfidence: number
  agedHazardMs: number
  recoveryStartMs: number | null
  intervalMs: number
}
