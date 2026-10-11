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
