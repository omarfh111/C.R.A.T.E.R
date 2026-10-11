import { z } from 'zod'
import { createLocalRequest, parseAssistantAnswer, type AssistantAnswer } from '../../integrations/m3-assistant-client'
import { telemetryFrameSchema } from '../telemetry/contract'

export const sessionSchema = z.object({ sessionId: z.uuid(), roverId: z.string().min(1).max(128), startedAt: z.iso.datetime({ offset: true }), endedAt: z.iso.datetime({ offset: true }).nullable(), phase: z.enum(['capturing', 'completed', 'interrupted']), provenance: z.enum(['synthetic', 'historical_replay', 'live_inference']), radioProvenance: z.literal('simulated'), authority: z.literal('m2-producer') })
export type IncidentSession = z.infer<typeof sessionSchema>
export const eventSchema = z.strictObject({ eventId: z.uuid(), sessionId: z.uuid(), kind: z.enum(['telemetry_stale', 'websocket_changed', 'radio_changed', 'dashboard_warning']), eventAt: z.iso.datetime({ offset: true }), receivedAt: z.iso.datetime({ offset: true }).nullable(), summary: z.string().min(1).max(1000), triggerKey: z.string().min(1).max(128), frame: telemetryFrameSchema.nullable() })
export type IncidentEvent = z.infer<typeof eventSchema>
const jobStates = ['waiting_capture', 'queued', 'waiting_service', 'running', 'completed', 'failed', 'cancelled', 'cancelling', 'interrupted', 'saturated', 'unavailable'] as const
const incidentSchema = z.object({ eventId:z.uuid(), sessionId:z.uuid(), roverId:z.string().min(1), kind:z.enum(['telemetry_stale','websocket_changed','radio_changed','producer_warning','dashboard_warning','operator_note']), eventAt:z.iso.datetime({offset:true}), recordedAt:z.iso.datetime({offset:true}), receivedAt:z.iso.datetime({offset:true}).nullable().optional(), summary:z.string().max(1000), question:z.string().max(2000), frame:telemetryFrameSchema.nullable().optional(), decision:z.string().max(1000).optional(), provenance:z.object({observation:z.enum(['synthetic','historical_replay','live_inference']),radio:z.literal('simulated'),reporter:z.enum(['m2-producer','dashboard-client-reported-v1']),certifiedMeasurement:z.literal(false)}), images:z.array(z.object({relativePath:z.string().max(300),sha256:z.string().regex(/^[a-f0-9]{64}$/),provenance:z.enum(['synthetic','historical_replay','live_capture','operator_supplied']),imageAnalysis:z.literal('not_performed')})).max(4), reviews:z.array(z.object({reviewId:z.uuid(),eventId:z.uuid(),verdict:z.enum(['confirmed','rejected','inconclusive']),note:z.string().min(1).max(1000),reviewedAt:z.iso.datetime({offset:true}),authority:z.literal('operator-reported')})).max(10).default([]), job:z.object({state:z.enum(jobStates),attempt:z.number().int().min(0).max(3),result:z.unknown().nullable(),error:z.string().max(2000).nullable(),updatedAt:z.iso.datetime({offset:true})}) })
export type Incident = Omit<z.infer<typeof incidentSchema>, 'job'> & { job: Omit<z.infer<typeof incidentSchema>['job'], 'result'> & {result:AssistantAnswer|null} }
export function parseIncidents(raw:unknown):Incident[] {
  const list = z.object({incidents:z.array(incidentSchema).max(20)}).parse(raw).incidents
  return list.map(i => {
    const result = i.job.result === null ? null : parseAssistantAnswer(i.job.result)
    if (result?.facts !== null && result !== null) throw new Error('Incident analysis cannot contain trusted mission facts')
    return {...i, job:{...i.job, result}}
  })
}
export function createIncidentClient(baseUrl:string) {
  const request = createLocalRequest({baseUrl,timeoutMs:5000})
  return {
    async sessions(signal?:AbortSignal) { return z.object({sessions:z.array(sessionSchema).max(20)}).parse(await request('/sessions',undefined,signal)).sessions },
    async incidents(signal?:AbortSignal) { return parseIncidents(await request('/incidents',undefined,signal)) },
    async record(event:IncidentEvent, signal?:AbortSignal) { eventSchema.parse(event); await request('/incidents',event,signal) },
    async action(eventId:string, action:'retry'|'cancel', signal?:AbortSignal) { z.uuid().parse(eventId); await request(`/jobs/${action}`,{eventId},signal) },
    async review(eventId:string, verdict:'confirmed'|'rejected'|'inconclusive', note:string) { z.uuid().parse(eventId); z.string().min(1).max(1000).parse(note); await request('/reviews',{eventId,verdict,note}) },
  }
}
