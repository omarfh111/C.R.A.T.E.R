/** Only accepted reducer state is inspected; silence never diagnoses calibration/tracking. */
import type { TelemetryState } from '../telemetry/state'
import type { IncidentEvent } from './incidentClient'

export function createIncidentDetector(sessionId:string) {
  let websocket:string|undefined, radio:string|undefined, receiptStale=false, captureStale=false, invalid=0
  return (state:TelemetryState, now:number, thresholdMs:number):IncidentEvent[] => {
    const events:IncidentEvent[] = [], receipt=state.latest, frame=receipt?.frame ?? null
    const emit = (kind:IncidentEvent['kind'], triggerKey:string, summary:string) => events.push({eventId:crypto.randomUUID(),sessionId,kind,triggerKey,summary,eventAt:new Date(now).toISOString(),receivedAt:receipt?.receivedAt??null,frame})
    if (websocket !== state.transportStatus) {
      emit('websocket_changed',`ws:${state.transportStatus}`,`Dashboard WebSocket ${websocket??'initial'} -> ${state.transportStatus}. This is transport status, not the declared rover radio state.`)
      websocket=state.transportStatus
    }
    if (frame && radio !== frame.link.status) {
      emit('radio_changed',`radio:${frame.link.status}`,`Accepted frame declares radio ${radio??'initial'} -> ${frame.link.status}. Counters describe the simulated radio channel at capture time.`)
      radio=frame.link.status
    }
    const rx=!!receipt && now-Date.parse(receipt.receivedAt)>thresholdMs
    const age=!!frame && now-Date.parse(frame.capturedAt)>thresholdMs
    if (rx && !receiptStale) emit('telemetry_stale','receipt_stale','No recent accepted telemetry receipt. WebSocket transport and last declared radio status remain separate; cause unknown.')
    if (age && !captureStale) emit('telemetry_stale','capture_stale','The accepted observation has an old capture timestamp. Historical replay is not fresh inference; no calibration or tracking failure is inferred.')
    receiptStale=rx; captureStale=age
    if (state.invalid>invalid) emit('dashboard_warning','invalid_packet','Dashboard rejected a packet against the canonical v1 contract. It did not become an accepted observation.')
    invalid=state.invalid
    return events
  }
}
