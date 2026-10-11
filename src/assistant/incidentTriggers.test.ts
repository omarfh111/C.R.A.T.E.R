import { describe,it,expect } from 'vitest'
import { createIncidentDetector } from './incidentTriggers'
import { initialTelemetryState, ingestTelemetry } from '../telemetry/state'
import { buildMockTimeline, defaultMockConfig } from '../telemetry/mock'
import { parseIncidents, createIncidentClient } from './incidentClient'

const session='00000000-0000-4000-8000-000000000001'
const receipt=()=>{const delivery=buildMockTimeline({...defaultMockConfig,lossEvery:0,duplicateEvery:0,reorderEvery:0,blackoutDurationTicks:0},100000).deliveries[0];return ingestTelemetry(initialTelemetryState,{type:'packet',raw:delivery.frame,receivedAt:new Date(100000).toISOString()})}
describe('automatic incidents from accepted state',()=>{
  it('separates transport, declared radio and receipt/capture age',()=>{
    const detect=createIncidentDetector(session), state=receipt()
    const first=detect(state,100000,3000)
    expect(first.filter(e=>e.kind==='radio_changed')).toHaveLength(1)
    expect(detect(state,100001,3000)).toHaveLength(0)
    const stale=detect({...state,transportStatus:'disconnected'},104000,3000)
    expect(stale.map(e=>e.triggerKey)).toEqual(['ws:disconnected','receipt_stale','capture_stale'])
    expect(stale.every(e=>e.frame===state.latest!.frame)).toBe(true)
    expect(detect({...state,transportStatus:'disconnected'},105000,3000)).toHaveLength(0)
    expect(stale.some(e=>/calibration_missing|tracking_warning/.test(e.kind))).toBe(false)
  })
  it('only accepted frames can change radio state and rejected packets produce warnings',()=>{
    const state=receipt(), detect=createIncidentDetector(session)
    detect(state,100000,3000)
    const bad=ingestTelemetry(state,{type:'packet',raw:{...state.latest!.frame,extra:'invalid'},receivedAt:new Date(100001).toISOString()})
    const events=detect(bad,100001,3000)
    expect(events.map(e=>e.kind)).toEqual(['dashboard_warning'])
    expect(events[0].frame).toBe(state.latest!.frame)
  })
  it('does not ask per frame and starts a new stale episode only after recovery',()=>{
    const state=receipt(),detect=createIncidentDetector(session)
    detect(state,100000,3000)
    for(let i=1;i<30;i++)expect(detect(state,100000+i,3000)).toHaveLength(0)
    expect(detect(state,104000,3000).filter(e=>e.kind==='telemetry_stale')).toHaveLength(2)
    detect({...state,latest:{...state.latest!,receivedAt:new Date(104001).toISOString()}},104001,3000)
    expect(detect({...state,latest:{...state.latest!,receivedAt:new Date(104001).toISOString()}},136000,3000).map(e=>e.triggerKey)).toEqual(['receipt_stale'])
  })
  it('rate limits available warnings and ignores counters from before activation',()=>{
    const state={...receipt(),invalid:10,sequenceGaps:4,outOfOrder:2},detect=createIncidentDetector(session)
    expect(detect(state,100000,3000).some(e=>e.kind==='dashboard_warning')).toBe(false)
    const warned={...state,sequenceGaps:5,outOfOrder:3}
    expect(detect(warned,100001,3000).map(e=>e.triggerKey)).toEqual(['out_of_order','sequence_gap'])
    expect(detect({...warned,sequenceGaps:6},100002,3000)).toHaveLength(0)
  })
  it('rejects fabricated provenance and generated facts in incident responses',()=>{
    expect(()=>parseIncidents({incidents:[{provenance:{certifiedMeasurement:true}}]})).toThrow()
    expect(()=>createIncidentClient('http://evil.test')).toThrow()
  })
})
