import { telemetryFrameSchema, type Hazard, type TelemetryReceipt } from './contract'
import type { AdapterEvent, TransportStatus } from './adapter'

export type TelemetryState = {
  transportStatus: TransportStatus
  latest: TelemetryReceipt | null
  hazards: Record<string, Hazard>
  lastSequenceByRover: Record<string, number>
  received: number
  accepted: number
  invalid: number
  duplicates: number
  outOfOrder: number
  sequenceGaps: number
}

export const initialTelemetryState: TelemetryState = {
  transportStatus: 'connecting', latest: null, hazards: {}, lastSequenceByRover: {},
  received: 0, accepted: 0, invalid: 0, duplicates: 0, outOfOrder: 0, sequenceGaps: 0,
}

export function ingestTelemetry(state: TelemetryState, event: AdapterEvent): TelemetryState {
  if (event.type === 'status') return { ...state, transportStatus: event.status }
  const received = state.received + 1
  let raw: unknown = event.raw
  if (typeof raw === 'string') {
    try { raw = JSON.parse(raw) } catch { return { ...state, received, invalid: state.invalid + 1 } }
  }
  const parsed = telemetryFrameSchema.safeParse(raw)
  if (!parsed.success || !Number.isFinite(Date.parse(event.receivedAt))) {
    return { ...state, received, invalid: state.invalid + 1 }
  }
  const frame = parsed.data
  const last = state.lastSequenceByRover[frame.roverId]
  if (last !== undefined && frame.sequence <= last) {
    return { ...state, received, duplicates: state.duplicates + Number(frame.sequence === last), outOfOrder: state.outOfOrder + Number(frame.sequence < last) }
  }
  const hazards = { ...state.hazards }
  for (const hazard of frame.hazards) hazards[`${frame.roverId}:${hazard.id}`] = hazard
  return {
    ...state, received, accepted: state.accepted + 1,
    sequenceGaps: state.sequenceGaps + (last === undefined ? 0 : Math.max(0, frame.sequence - last - 1)),
    lastSequenceByRover: { ...state.lastSequenceByRover, [frame.roverId]: frame.sequence },
    latest: { frame, receivedAt: event.receivedAt }, hazards,
  }
}
