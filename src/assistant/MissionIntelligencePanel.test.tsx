// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MissionIntelligencePanel } from './MissionIntelligencePanel'
import type { MissionIntelligence } from './missionIntelligence'
const intel: MissionIntelligence = {
  sequence:4,summary:'SEQ 4 · ACCEPTED EVIDENCE',stale:false,
  facts:[{label:'Rover fix',text:'E 1.00 · N 2.00 · U 0.00 m in LOCAL_ENU_V1.'}],
  limitations:'No mission decisions are inferred.',
}
const health={status:'ready',httpReady:true,modelStatus:'available',busy:false,indexedChunks:13,llm:'qwen3:4b',embedding:'embeddinggemma:300m'}
const answer={status:'answered',answer:'NASA uses onboard navigation [S1].',sources:[{sourceId:'S1',path:'docs/knowledge/nasa.md',lineStart:1,lineEnd:2,digest:'a'.repeat(64),score:.9,text:'NASA describes autonomous driving.',sourceUrl:'https://science.nasa.gov/example',verifiedOn:'2026-10-10'}],citedSourceIds:['S1'],facts:null,models:{llm:'qwen3:4b',embedding:'embeddinggemma:300m'},roles:['explainer'],limitations:'Unverified explanation; no rover control.'}
const response=(value:unknown,status=200)=>new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json'}})
function openScience() { fireEvent.click(screen.getByText('LOCAL AI · SCIENCE CONTEXT')) }
async function connect() { openScience();fireEvent.click(screen.getByRole('button',{name:'CONNECT LOCAL AI'}));await screen.findByText('HTTP READY') }
afterEach(()=>{cleanup();vi.unstubAllGlobals()})
describe('optional Mission Intelligence inspector',()=>{
  it('shows deterministic accepted values immediately and makes no default network request',()=>{
    const fetch=vi.fn();vi.stubGlobal('fetch',fetch)
    render(<MissionIntelligencePanel intelligence={intel}/>);
    expect(screen.getByText('E 1.00 · N 2.00 · U 0.00 m in LOCAL_ENU_V1.')).toBeTruthy()
    expect(fetch).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button',{name:/MISSION INTELLIGENCE/}))
    expect(screen.queryByText('E 1.00 · N 2.00 · U 0.00 m in LOCAL_ENU_V1.')).toBeNull()
    expect(fetch).not.toHaveBeenCalled()
  })
  it('connects explicitly and displays a real-shaped answer, evidence and limitations separately',async()=>{
    const fetch=vi.fn(async(url:string,_options:RequestInit)=>response(url.endsWith('/health')?health:answer));vi.stubGlobal('fetch',fetch)
    render(<MissionIntelligencePanel intelligence={intel}/>);await connect()
    expect(fetch).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByRole('button',{name:'ASK REFERENCES'}))
    await screen.findByText(answer.answer)
    expect(screen.getByText('UNVERIFIED GENERATED TEXT · SEPARATE FROM MISSION FACTS')).toBeTruthy()
    expect(screen.getByText(answer.limitations)).toBeTruthy()
    fireEvent.click(screen.getByText(/\[S1\] nasa.md/))
    expect(screen.getByText('NASA describes autonomous driving.')).toBeTruthy()
    expect(screen.getByRole('link',{name:'Open source reference ↗'}).getAttribute('href')).toBe(answer.sources[0].sourceUrl)
    expect(screen.getByText('E 1.00 · N 2.00 · U 0.00 m in LOCAL_ENU_V1.')).toBeTruthy()
    const sent=JSON.parse(fetch.mock.calls[1][1]?.body as string)
    expect(Object.keys(sent).sort()).toEqual(['question','topK'])
  })
  it('renders hostile model and source content as plain text and never changes accepted mission facts',async()=>{
    const hostile={...answer,answer:'<img src=x onerror=alert(1)> unsupported 999 K [S1].',facts:{temperature:999},sources:[{...answer.sources[0],text:'<script>alert(1)</script>'}]}
    vi.stubGlobal('fetch',vi.fn(async(url:string)=>response(url.endsWith('/health')?health:hostile)))
    render(<MissionIntelligencePanel intelligence={intel}/>);await connect();fireEvent.click(screen.getByRole('button',{name:'ASK REFERENCES'}))
    await screen.findByText(hostile.answer)
    fireEvent.click(screen.getByText(/\[S1\] nasa.md/))
    expect(screen.getByText('<script>alert(1)</script>')).toBeTruthy()
    const panel=screen.getByRole('region',{name:'Mission Intelligence'})
    expect(panel.querySelector('script')).toBeNull();expect(panel.querySelector('img')).toBeNull()
    expect(within(panel).getByText('E 1.00 · N 2.00 · U 0.00 m in LOCAL_ENU_V1.')).toBeTruthy()
    expect(panel.textContent).not.toContain('temperature:999')
  })
  it.each([['busy',429,'BUSY'],['timeout',504,'TIMED OUT'],['unavailable',503,'UNAVAILABLE'],['invalid_response',502,'INVALID RESPONSE'],['failed',500,'FAILED']])('shows %s without damaging deterministic intelligence',async(code,status,label)=>{
    vi.stubGlobal('fetch',vi.fn(async(url:string)=>response(url.endsWith('/health')?health:{code,error:'unsafe untrusted error'},Number(url.endsWith('/health')?200:status))))
    render(<MissionIntelligencePanel intelligence={intel}/>);await connect();fireEvent.click(screen.getByRole('button',{name:'ASK REFERENCES'}))
    await screen.findByText(String(label))
    expect(screen.getByText('E 1.00 · N 2.00 · U 0.00 m in LOCAL_ENU_V1.')).toBeTruthy()
    expect(screen.queryByText('unsafe untrusted error')).toBeNull()
  })
  it('distinguishes HTTP-ready service from missing models and disables generation',async()=>{
    vi.stubGlobal('fetch',vi.fn(async()=>response({...health,modelStatus:'unavailable'})))
    render(<MissionIntelligencePanel intelligence={intel}/>);openScience();fireEvent.click(screen.getByRole('button',{name:'CONNECT LOCAL AI'}))
    await screen.findByText('UNAVAILABLE')
    expect((screen.getByRole('button',{name:'ASK REFERENCES'}) as HTMLButtonElement).disabled).toBe(true)
  })
  it('requires recovery after a backend deadline rather than offering another inference',async()=>{
    vi.stubGlobal('fetch',vi.fn(async()=>response({...health,busy:true,inferenceState:'timeout_requires_restart'})))
    render(<MissionIntelligencePanel intelligence={intel}/>);openScience();fireEvent.click(screen.getByRole('button',{name:'CONNECT LOCAL AI'}))
    await screen.findByText('TIMED OUT')
    expect(screen.getByRole('status').textContent).toContain('restart the sidecar')
    expect((screen.getByRole('button',{name:'ASK REFERENCES'}) as HTMLButtonElement).disabled).toBe(true)
  })
  it('blocks optional generation while a live M1 capture is active',async()=>{
    vi.stubGlobal('fetch',vi.fn(async()=>response({...health,busy:true,inferenceState:'capture_blocked'})))
    render(<MissionIntelligencePanel intelligence={intel}/>);openScience();fireEvent.click(screen.getByRole('button',{name:'CONNECT LOCAL AI'}))
    await screen.findByText('BUSY')
    expect(screen.getByRole('status').textContent).toContain('preserve perception')
    expect((screen.getByRole('button',{name:'ASK REFERENCES'}) as HTMLButtonElement).disabled).toBe(true)
  })
  it('shows insufficient evidence as an explicit normal result',async()=>{
    vi.stubGlobal('fetch',vi.fn(async(url:string)=>response(url.endsWith('/health')?health:{...answer,status:'insufficient_evidence',answer:'No temperature measurement is available.',sources:[],citedSourceIds:[]})))
    render(<MissionIntelligencePanel intelligence={intel}/>);await connect();fireEvent.click(screen.getByRole('button',{name:'ASK REFERENCES'}))
    await screen.findByText('INSUFFICIENT EVIDENCE');expect(screen.getByText('No temperature measurement is available.')).toBeTruthy()
  })
  it('rejects mismatched citations before displaying answer text',async()=>{
    vi.stubGlobal('fetch',vi.fn(async(url:string)=>response(url.endsWith('/health')?health:{...answer,answer:'False reading [S99].'})))
    render(<MissionIntelligencePanel intelligence={intel}/>);await connect();fireEvent.click(screen.getByRole('button',{name:'ASK REFERENCES'}))
    await screen.findByText('INVALID RESPONSE');expect(screen.queryByText('False reading [S99].')).toBeNull()
  })
  it('cancels a request with an honest backend-termination limitation',async()=>{
    vi.stubGlobal('fetch',vi.fn(async(url:string,options:RequestInit)=>url.endsWith('/health')?response(health):new Promise<Response>((_resolve,reject)=>options.signal?.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')),{once:true}))))
    render(<MissionIntelligencePanel intelligence={intel}/>);await connect();fireEvent.click(screen.getByRole('button',{name:'ASK REFERENCES'}));await screen.findByText('GENERATING')
    fireEvent.click(screen.getByRole('button',{name:'CANCEL REQUEST'}));await screen.findByText('CANCELLED')
    await waitFor(()=>expect(screen.getByRole('status').textContent).toContain('may continue'))
  })
})
