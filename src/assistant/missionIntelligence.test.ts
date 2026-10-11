import { describe, expect, it } from 'vitest'
import { ingestTelemetry, initialTelemetryState } from '../telemetry/state'
import { buildMockTimeline, defaultMockConfig } from '../telemetry/mock'
import type { MapHazard } from '../mission-control/model/types'
import { deriveMissionIntelligence } from './missionIntelligence'
const now = Date.parse('2026-10-11T00:00:00Z')
const frame = buildMockTimeline(defaultMockConfig, now - 4000).generated[4]
const state = ingestTelemetry(initialTelemetryState, { type: 'packet', raw: frame, receivedAt: new Date(now).toISOString() })
describe('deterministic Mission Intelligence', () => {
  it('uses only accepted frame values and separates confidence, uncertainty and geometry', () => {
    const h=frame.hazards[0]
    const selected: MapHazard = {key:`${frame.roverId}:${h.id}`,id:h.id,type:h.type,x:h.position.xM,y:h.position.yM,z:h.position.zM,unc:h.uncertaintyRadiusM,confidence:h.confidence,observedMs:Date.parse(h.observedAt),ageMs:0,firstRxMs:now}
    const before=JSON.stringify(state)
    const v=deriveMissionIntelligence(state,selected,now,10_000,'LIVE')
    expect(v.sequence).toBe(frame.sequence)
    expect(v.facts.find(f=>f.label==='Hazard location')?.text).toContain(`E ${h.position.xM.toFixed(2)}`)
    expect(v.facts.find(f=>f.label==='Evidence quality')?.text).toContain(h.confidence.toFixed(2))
    expect(v.facts.find(f=>f.label==='Evidence quality')?.text).toContain('not position accuracy')
    expect(v.facts.find(f=>f.label==='Channel report')?.text).toContain(`${frame.link.packetsSent} packets sent, ${frame.link.packetsLost} lost`)
    expect(JSON.stringify(state)).toBe(before)
  })
  it('keeps historical captures stale even when newly received', () => {
    const historical={...frame,capturedAt:'2026-01-01T00:00:00Z',hazards:[]}
    const accepted=ingestTelemetry(initialTelemetryState,{type:'packet',raw:historical,receivedAt:new Date(now).toISOString()})
    const v=deriveMissionIntelligence(accepted,null,now,10_000,'LIVE')
    expect(v.stale).toBe(true)
    expect(v.facts.find(f=>f.label==='Information age')?.text).toContain('recent receipt does not make it current')
    expect(v.facts.find(f=>f.label==='Provenance')?.text).toContain('does not certify measured versus simulated')
  })
  it('does not infer radio failure, calibration or a position when no frame exists', () => {
    const v=deriveMissionIntelligence(initialTelemetryState,null,now,10_000,'LIVE')
    expect(v.sequence).toBeNull(); expect(v.facts).toEqual([])
  })
  it('does not display rejected invalid observations', () => {
    const rejected=ingestTelemetry(state,{type:'packet',raw:{...frame,sequence:100,roverPosition:{...frame.roverPosition,xM:'999'}},receivedAt:new Date(now).toISOString()})
    const v=deriveMissionIntelligence(rejected,null,now,10_000,'MOCK')
    expect(v.sequence).toBe(frame.sequence)
    expect(v.facts.find(f=>f.label==='Provenance')?.text).toContain('simulated')
  })
})

// A retained hazard is not made fresh by receiving a newer rover fix.
it('labels an older selected observation independently of the latest accepted frame', () => {
  const h=frame.hazards[0]
  const selected: MapHazard={key:`${frame.roverId}:${h.id}`,id:h.id,type:h.type,x:h.position.xM,y:h.position.yM,z:h.position.zM,unc:h.uncertaintyRadiusM,confidence:h.confidence,observedMs:now-60_000,ageMs:60_000,firstRxMs:now-60_000}
  const v=deriveMissionIntelligence(state,selected,now,10_000,'LIVE')
  expect(v.stale).toBe(true)
  expect(v.summary).toContain('AGED OBSERVATION')
  expect(v.facts.find(f=>f.label==='Observation')?.text).toContain('60.0 s')
  const other=deriveMissionIntelligence(state,{...selected,key:'other-rover:hazard'},now,10_000,'LIVE')
  expect(other.facts.find(f=>f.label==='Hazard location')?.text).toContain('No separation is calculated against a different rover')
})
