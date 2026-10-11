// @vitest-environment jsdom
import { afterEach,expect,it,vi } from 'vitest'
import { cleanup,fireEvent,render,screen,waitFor } from '@testing-library/react'
import { IncidentDialogue } from './IncidentDialogue'
import { initialTelemetryState } from '../telemetry/state'
const session={sessionId:'00000000-0000-4000-8000-000000000001',roverId:'rover-1',startedAt:'2026-10-11T03:00:00Z',endedAt:null,phase:'capturing',provenance:'historical_replay',radioProvenance:'simulated',authority:'m2-producer'}
const incident={eventId:'00000000-0000-4000-8000-000000000002',sessionId:session.sessionId,roverId:'rover-1',kind:'telemetry_stale',eventAt:session.startedAt,recordedAt:session.startedAt,summary:'No recent receipt; cause unknown',question:'Explain evidence limitations',provenance:{observation:'historical_replay',radio:'simulated',reporter:'dashboard-client-reported-v1',certifiedMeasurement:false},images:[],job:{state:'waiting_capture',attempt:0,result:null,error:null,updatedAt:session.startedAt}}
afterEach(()=>{cleanup();vi.unstubAllGlobals();localStorage.clear()})
it('is inert by default and unavailable collection cannot break rendering',async()=>{
 const fetch=vi.fn().mockRejectedValue(new Error('offline'));vi.stubGlobal('fetch',fetch)
 render(<IncidentDialogue state={initialTelemetryState} mode="LIVE" now={Date.now()} staleThresholdMs={3000}/>)
 expect(fetch).not.toHaveBeenCalled()
 fireEvent.click(screen.getByText('CONNECT JOURNAL'))
 await screen.findByText(/Collector unavailable or response invalid/)
 expect(screen.getByText(/Automatic incident questions are separate/)).toBeTruthy()
})
it('shows automatic questions, persistent job states and sources separately from user chat',async()=>{
 vi.stubGlobal('fetch',vi.fn(async(url:string)=>new Response(JSON.stringify(url.endsWith('/sessions')?{sessions:[session]}:{incidents:[incident]}),{headers:{'content-type':'application/json'}})))
 render(<IncidentDialogue state={initialTelemetryState} mode="LIVE" now={Date.now()} staleThresholdMs={3000}/>)
 fireEvent.click(screen.getByText('CONNECT JOURNAL'))
 await screen.findByLabelText('Producer session')
 expect(screen.getByText('AUTOMATIC QUESTION')).toBeTruthy()
 expect(screen.getByText('Explain evidence limitations')).toBeTruthy()
 expect(screen.getAllByText(/WAITING FOR PRODUCER CAPTURE END/)[0]).toBeTruthy()
 expect(screen.queryByLabelText('Science question')).toBeNull()
})
it('retains unsent events durably when collector becomes unavailable',async()=>{
 vi.stubGlobal('fetch',vi.fn(async(url:string,options:RequestInit)=>{
  if(options.method==='POST')throw new Error('offline')
  return new Response(JSON.stringify(url.endsWith('/sessions')?{sessions:[session]}:{incidents:[]}),{headers:{'content-type':'application/json'}})
 }))
 render(<IncidentDialogue state={initialTelemetryState} mode="LIVE" now={Date.now()} staleThresholdMs={3000}/>)
 fireEvent.click(screen.getByText('CONNECT JOURNAL'));await screen.findByLabelText('Producer session')
 fireEvent.change(screen.getByLabelText('Producer session'),{target:{value:session.sessionId}})
 await waitFor(()=>expect(localStorage.getItem(`crater-incident-outbox:http://127.0.0.1:8767:${session.sessionId}`)).toContain('websocket_changed'))
 await screen.findByText(/Pending events are retained locally/)
})

it('never attaches a new observation to an ended producer session',async()=>{
 const {buildMockTimeline,defaultMockConfig}=await import('../telemetry/mock')
 const now=Date.now(),frame=buildMockTimeline(defaultMockConfig,now).deliveries[0].frame
 const ended={...session,phase:'completed',endedAt:new Date(now-1000).toISOString()}
 const fetch=vi.fn(async(url:string,_options?:RequestInit)=>new Response(JSON.stringify(url.endsWith('/sessions')?{sessions:[ended]}:{incidents:[]}),{headers:{'content-type':'application/json'}}));vi.stubGlobal('fetch',fetch)
 const state={...initialTelemetryState,latest:{frame,receivedAt:new Date(now).toISOString()},accepted:1}
 render(<IncidentDialogue state={state} mode="LIVE" now={now} staleThresholdMs={3000}/>)
 fireEvent.click(screen.getByText('CONNECT JOURNAL'));await screen.findByLabelText('Producer session')
 fireEvent.change(screen.getByLabelText('Producer session'),{target:{value:session.sessionId}})
 await screen.findByText(/Selected session does not match this new observation/)
 expect(fetch.mock.calls.some(call=>(call[1] as RequestInit|undefined)?.method==='POST')).toBe(false)
})

it('pauses a rejected event without blocking session refresh',async()=>{
 const fetch=vi.fn(async(url:string,options?:RequestInit)=>{
  if(options?.method==='POST')return new Response(JSON.stringify({code:'invalid_request'}),{status:400,headers:{'content-type':'application/json'}})
  return new Response(JSON.stringify(url.endsWith('/sessions')?{sessions:[session]}:{incidents:[]}),{headers:{'content-type':'application/json'}})
 });vi.stubGlobal('fetch',fetch)
 render(<IncidentDialogue state={initialTelemetryState} mode="LIVE" now={Date.now()} staleThresholdMs={3000}/>)
 fireEvent.click(screen.getByText('CONNECT JOURNAL'));await screen.findByLabelText('Producer session')
 fireEvent.change(screen.getByLabelText('Producer session'),{target:{value:session.sessionId}})
 await screen.findByText('RETRY PENDING EVENTS')
 expect(fetch.mock.calls.filter(call=>call[1]?.method==='POST')).toHaveLength(1)
 expect(localStorage.getItem(`crater-incident-outbox:http://127.0.0.1:8767:${session.sessionId}`)).toContain('websocket_changed')
 expect(fetch.mock.calls.filter(call=>call[0].endsWith('/sessions')).length).toBeGreaterThan(1)
})

it('shows capture completion without claiming a new mismatched observation',async()=>{
 const ended={...session,phase:'completed',endedAt:new Date(Date.now()-60000).toISOString()}
 const fetch=vi.fn(async(url:string,_options?:RequestInit)=>new Response(JSON.stringify(url.endsWith('/sessions')?{sessions:[ended]}:{incidents:[]}),{headers:{'content-type':'application/json'}}));vi.stubGlobal('fetch',fetch)
 render(<IncidentDialogue state={initialTelemetryState} mode="LIVE" now={Date.now()} staleThresholdMs={3000}/>)
 fireEvent.click(screen.getByText('CONNECT JOURNAL'));await screen.findByLabelText('Producer session')
 fireEvent.change(screen.getByLabelText('Producer session'),{target:{value:session.sessionId}})
 await screen.findByText(/Capture completed; incident collection is closed/)
 expect(fetch.mock.calls.some(call=>call[1]?.method==='POST')).toBe(false)
})
