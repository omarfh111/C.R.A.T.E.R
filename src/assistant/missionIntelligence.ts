import type { TelemetryState } from '../telemetry/state'
import type { MapHazard } from '../mission-control/model/types'

export type IntelligenceFact = { label: string; text: string }
export type MissionIntelligence = { sequence: number | null; summary: string; stale: boolean; facts: IntelligenceFact[]; limitations: string }
const seconds = (ms: number) => `${(ms / 1000).toFixed(1)} s`
const point = (x: number, y: number, z: number) => `E ${x.toFixed(2)} · N ${y.toFixed(2)} · U ${z.toFixed(2)} m`

/** Pure derivation from already accepted telemetry. No model, inference, or state mutation. */
export function deriveMissionIntelligence(state: TelemetryState, selected: MapHazard | null, nowMs: number, staleMs: number, mode: 'MOCK' | 'LIVE'): MissionIntelligence {
  const receipt = state.latest
  if (!receipt) return {
    sequence: null, summary: 'Waiting for a validated rover observation.', stale: false, facts: [],
    limitations: 'No position, hazard, or radio measurement is available until a frame is accepted.',
  }
  const f = receipt.frame
  const captured = Date.parse(f.capturedAt), received = Date.parse(receipt.receivedAt)
  const captureAge = Math.max(0, nowMs - captured), receiptAge = Math.max(0, nowMs - received)
  const frameStale = captureAge > staleMs
  const observationAge = selected ? Math.max(0, nowMs - selected.observedMs) : null
  const observationStale = observationAge !== null && observationAge > staleMs
  const stale = frameStale || observationStale
  const sameRover = !!selected && selected.key === `${f.roverId}:${selected.id}`
  const facts: IntelligenceFact[] = [
    { label: 'Observation', text: selected ? `${selected.type.toUpperCase()} ${selected.id}, retained from accepted telemetry. Observed ${new Date(selected.observedMs).toISOString()}; observation age ${seconds(observationAge ?? 0)}${observationStale ? ' (older than the configured stale threshold)' : ''}.` : `Frame ${f.sequence} reports ${f.hazards.length} hazard observation${f.hazards.length === 1 ? '' : 's'}. Select a hazard to inspect its calculated location.` },
    { label: selected ? 'Hazard location' : 'Rover fix', text: selected ? `${point(selected.x, selected.y, selected.z)} in LOCAL_ENU_V1. ${sameRover ? `Horizontal separation from the latest rover fix: ${Math.hypot(selected.x - f.roverPosition.xM, selected.y - f.roverPosition.yM).toFixed(2)} m; the observations may have different capture times.` : 'No separation is calculated against a different rover.'}` : `${point(f.roverPosition.xM, f.roverPosition.yM, f.roverPosition.zM)} in LOCAL_ENU_V1; transmitted position uncertainty radius ${f.positionUncertaintyRadiusM.toFixed(2)} m.` },
    { label: 'Evidence quality', text: selected ? `Detector confidence ${selected.confidence.toFixed(2)} / 1.00; transmitted location uncertainty radius ${selected.unc.toFixed(2)} m. Confidence is a detector score, not position accuracy or a calibrated probability. The radius is not a certified statistical interval.` : 'Coordinates are a transmitted local geometric estimate. Telemetry does not identify camera calibration, image pixels, or the inference backend.' },
    { label: 'Information age', text: `Captured ${f.capturedAt}; accepted ${receipt.receivedAt}. Capture age ${seconds(captureAge)}; receipt age ${seconds(receiptAge)}. ${captured > nowMs || received > nowMs ? 'Clock alignment is not established; freshness is unknown.' : frameStale ? `Older than the ${seconds(staleMs)} stale threshold; recent receipt does not make it current.` : 'Within the configured stale threshold.'}${received >= captured ? ` Capture-to-receipt interval ${seconds(received - captured)}; this includes replay age and clock differences, not only network latency.` : ' Capture time is ahead of receipt time; clock alignment is not established.'}` },
    { label: 'Channel report', text: `At frame ${f.sequence}: rover link ${f.link.status}; ${f.link.packetsSent} packets sent, ${f.link.packetsLost} lost. Mission Control has accepted ${state.accepted} frames and inferred ${state.sequenceGaps} sequence gaps. Station transport is ${state.transportStatus}; these are distinct observations, not proof of a radio-failure cause.` },
    { label: 'Provenance', text: mode === 'MOCK' ? 'MOCK is a simulated scenario: observations and communication interruptions are simulated.' : 'LIVE describes the WebSocket connection. The v1 frame does not certify measured versus simulated data. The Quick Demo replays historical ONNX detections from a synthetic calibrated scene and simulates radio interruptions.' },
  ]
  return {
    sequence: f.sequence, stale,
    summary: selected ? `${selected.id} · ${selected.type.toUpperCase()} · ${observationStale ? 'AGED OBSERVATION' : frameStale ? 'STALE FRAME' : 'ACCEPTED EVIDENCE'}` : `SEQ ${f.sequence} · ${stale ? 'STALE FRAME' : 'ACCEPTED EVIDENCE'}`,
    facts,
    limitations: 'Read-only explanation of accepted values. No new observations, calibration claims, coordinates, or mission decisions are inferred. NASA/ESA research provides context and does not validate this rover.',
  }
}
