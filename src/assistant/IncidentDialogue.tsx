import { useEffect, useRef, useState } from 'react'
import type { TelemetryState } from '../telemetry/state'
import { createIncidentClient, eventSchema, type Incident, type IncidentEvent, type IncidentSession } from './incidentClient'
import { createIncidentDetector } from './incidentTriggers'

type Props={state:TelemetryState;mode:string;now:number;staleThresholdMs:number}
const stateLabels:Record<Incident['job']['state'],string>={waiting_capture:'WAITING FOR PRODUCER CAPTURE END',queued:'QUEUED AFTER CAPTURE',waiting_service:'WAITING FOR LOCAL AI',running:'ANALYZING',completed:'ANALYSIS COMPLETE',failed:'FAILED',cancelled:'CANCELLED',cancelling:'CANCELLING · BACKEND MAY STILL RUN',interrupted:'INTERRUPTED · REVIEW BEFORE RETRY',saturated:'QUEUE FULL · INCIDENT SAVED',unavailable:'UNAVAILABLE · RETRY REQUIRED'}
export function IncidentDialogue({state,mode,now,staleThresholdMs}:Props) {
  const [url,setUrl]=useState('http://127.0.0.1:8767'),[connected,setConnected]=useState(false),[connecting,setConnecting]=useState(false),[sessions,setSessions]=useState<IncidentSession[]>([]),[sessionId,setSessionId]=useState(''),[incidents,setIncidents]=useState<Incident[]>([]),[message,setMessage]=useState('Optional persistent incident collection. No model is required to record events.'),[reviewId,setReviewId]=useState(''),[reviewNote,setReviewNote]=useState('')
  const generation=useRef(0)
  const client=useRef<ReturnType<typeof createIncidentClient>|null>(null), current=useRef({state,now}), outbox=useRef<IncidentEvent[]>([]), storageKey=useRef(''), enabled=useRef(false), pending=useRef(false), controller=useRef<AbortController|null>(null)
  current.current={state,now}
  function disconnect() { generation.current++;setConnecting(false);enabled.current=false; controller.current?.abort(); setConnected(false); client.current=null; setMessage('Collector disconnected. Already persisted jobs continue; no telemetry is modified.') }
  useEffect(()=>()=>{generation.current++;enabled.current=false;controller.current?.abort()},[])
  async function connect() {
    const id=++generation.current;setConnecting(true)
    controller.current?.abort();const control=new AbortController();controller.current=control
    try {
      const service=createIncidentClient(url), available=await service.sessions(control.signal)
      const rows=await service.incidents(control.signal)
      if(id!==generation.current)return
      client.current=service;setSessions(available);setSessionId('');setIncidents(rows);enabled.current=true;setConnected(true)
      setMessage(available.length?'Choose the producer session matching this rover/capture.':'Waiting for M2 started with CRATER_INCIDENT_JOURNAL. Reconnect when its session is created.')
    } catch {if(id===generation.current){setMessage('Collector unavailable or response invalid. Check its exact allowed dashboard origin.');setConnected(false)}}finally{if(id===generation.current)setConnecting(false)}
  }
  useEffect(()=>{
    if (!connected||!sessionId||mode!=='LIVE') return
    const session=sessions.find(s=>s.sessionId===sessionId)
    if (!session) return
    const detect=createIncidentDetector(sessionId)
    storageKey.current=`crater-incident-outbox:${url}:${sessionId}`
    try {const raw=JSON.parse(localStorage.getItem(storageKey.current)??'[]');outbox.current=eventSchema.array().max(32).parse(raw);if(outbox.current.some(e=>e.sessionId!==sessionId))throw new Error("outbox session mismatch")} catch {outbox.current=[];setMessage('Local outbox could not be restored. Previously persisted server incidents remain available.')}
    const persist=()=>{try {localStorage.setItem(storageKey.current,JSON.stringify(outbox.current))} catch {setMessage('Browser outbox storage unavailable. Keep this page open until events are persisted.')}}
    let disposed=false, ticks=0
    const tick=async()=>{
      if(disposed||!enabled.current||pending.current||!client.current)return
      const snapshot=current.current
      if(snapshot.state.latest && snapshot.state.latest.frame.roverId!==session.roverId){setMessage('Selected session rover differs from the accepted observation; collection paused.');return}
      const receipt=snapshot.state.latest
      const inSession=receipt && Date.parse(receipt.receivedAt)>=Date.parse(session.startedAt) && (!session.endedAt||Date.parse(receipt.receivedAt)<=Date.parse(session.endedAt))
      const events=detect(inSession?snapshot.state:{...snapshot.state,latest:null},snapshot.now,staleThresholdMs)
      if(events.length){const room=32-outbox.current.length;outbox.current.push(...events.slice(0,room));persist();if(events.length>room)setMessage('Browser outbox full. Some new incidents were not saved; telemetry continues.')}
      pending.current=true
      try {
        if(outbox.current.length){await client.current.record(outbox.current[0],controller.current?.signal);if(disposed)return;outbox.current.shift();persist()}
        if(ticks++%3===0){const rows=await client.current.incidents(controller.current?.signal);if(!disposed)setIncidents(rows)}
        if(!disposed)setMessage(`${outbox.current.length} pending browser events. Analyses require explicit producer completion and an idle guarded AI service.`)
      }catch {if(!disposed)setMessage('Collector unavailable or invalid response. Pending events are retained locally; bounded retry continues.')}finally{pending.current=false}
    }
    void tick();const timer=setInterval(()=>void tick(),1000)
    return()=>{disposed=true;clearInterval(timer)}
  },[connected,sessionId,sessions,mode,url,staleThresholdMs])
  async function action(id:string, name:'retry'|'cancel') {try{await client.current?.action(id,name);setIncidents(await client.current!.incidents())}catch{setMessage('Action rejected or collector unavailable; check queue/attempt limits.')}}
  async function review(verdict:'confirmed'|'rejected'|'inconclusive') {try{await client.current?.review(reviewId,verdict,reviewNote);setIncidents(await client.current!.incidents());setReviewId('');setReviewNote('');setMessage('Operator review stored separately. Generated text has not become a trusted observation.')}catch{setMessage('Review not saved. Supply a note and check collector availability.')}}
  return <details className="mi__science"><summary><span>ROBOT INCIDENT DIALOGUE</span><span className="mi__optional">POST-CAPTURE · OPTIONAL</span></summary><div className="mi__science-body">
    <p className="mi__note">Automatic incident questions are separate from your science questions. No driving, hazard mutation or image understanding.</p>
    <label className="mi__field">Incident collector URL<input aria-label="Incident collector URL" value={url} disabled={connected||connecting} onChange={e=>setUrl(e.target.value)} /></label>
    <div className="mi__actions"><button onClick={()=>void connect()} disabled={connected||connecting}>CONNECT JOURNAL</button>{connected&&<button onClick={disconnect}>DISCONNECT JOURNAL</button>}</div>
    {connected&&<label className="mi__field">Producer session<select aria-label="Producer session" value={sessionId} onChange={e=>setSessionId(e.target.value)}><option value="">Select capture session</option>{sessions.map(s=><option value={s.sessionId} key={s.sessionId}>{s.roverId} · {s.provenance} · {s.sessionId.slice(0,8)} · {s.phase}</option>)}</select></label>}
    <p className="mi__note" role="status">{mode!=='LIVE'?'Automatic collection is available in LIVE mode only.':message}</p>
    {incidents.filter(i=>!sessionId||i.sessionId===sessionId).map(i=><details className="mi__source" key={i.eventId}><summary>{i.kind.replaceAll('_',' ')} · {stateLabels[i.job.state]}</summary>
      <p className="mi__note">{i.summary}</p><p className="mi__source-meta">Incident {i.eventId}<br/>Session {i.sessionId}<br/>Triggered {i.eventAt}<br/>Captured {i.frame?.capturedAt??'no observation'}<br/>Received {i.receivedAt??'not available'}<br/>{i.provenance.observation} · radio {i.provenance.radio} · {i.provenance.reporter}</p>
      {i.frame&&<p className="mi__note">Accepted snapshot #{i.frame.sequence} · declared radio {i.frame.link.status} · {i.frame.link.packetsLost}/{i.frame.link.packetsSent} packets lost/sent. {i.frame.hazards.length} accepted hazards. Values remain in the stored observation.</p>}
      <p className="mi__answer-label">AUTOMATIC QUESTION</p><p className="mi__note">{i.question}</p><p className="mi__source-meta">{stateLabels[i.job.state]} · attempt {i.job.attempt}/3</p>
      {i.job.error&&<p className="mi__limitations">{i.job.error}</p>}
      {i.job.result&&<><span className="mi__answer-label">{i.job.result.status==='answered'?'UNVERIFIED GENERATED EXPLANATION':'INSUFFICIENT EVIDENCE'}</span><p className="mi__answer-text">{i.job.result.answer}</p>{i.job.result.sources.map(s=><details className="mi__source" key={s.sourceId}><summary>[{s.sourceId}] {s.path.split(/[\\/]/).pop()}</summary><blockquote>{s.text}</blockquote>{s.sourceUrl&&<a href={s.sourceUrl} target="_blank" rel="noopener noreferrer">Source reference ↗</a>}<p className="mi__source-meta">SHA-256 {s.digest}</p></details>)}<p className="mi__limitations">{i.job.result.limitations}</p></>}
      {i.images.length>0&&<p className="mi__note">{i.images.length} controlled image reference(s), SHA-256 recorded. Image analysis not performed.</p>}
      {i.reviews.length>0&&<details className="mi__sources"><summary>SEPARATE OPERATOR REVIEWS · {i.reviews.length}</summary>{i.reviews.map(r=><p className="mi__note" key={r.reviewId}>{r.verdict.toUpperCase()} · {r.reviewedAt}<br/>{r.note}<br/>Operator-reported; no automatic promotion into mission facts.</p>)}</details>}
      {i.decision&&<p className="mi__note">Explicitly supplied decision: {i.decision}</p>}
      <div className="mi__actions">{['failed','interrupted','saturated','unavailable','cancelled'].includes(i.job.state)&&i.job.attempt<3&&<button onClick={()=>void action(i.eventId,'retry')}>RETRY ANALYSIS</button>}{['waiting_capture','waiting_service','queued','running'].includes(i.job.state)&&<button onClick={()=>void action(i.eventId,'cancel')}>CANCEL JOB</button>}<button onClick={()=>setReviewId(i.eventId)}>REVIEW SEPARATELY</button></div>
      {reviewId===i.eventId&&<div><label className="mi__field">Operator review note<textarea aria-label="Operator review note" maxLength={1000} value={reviewNote} onChange={e=>setReviewNote(e.target.value)}/></label><div className="mi__actions">{(['confirmed','rejected','inconclusive'] as const).map(v=><button key={v} disabled={!reviewNote.trim()} onClick={()=>void review(v)}>{v.toUpperCase()}</button>)}</div></div>}
    </details>)}<p className="mi__note mi__footnote">A stopped producer without a completion marker requires explicit recovery. A cancelled backend inference may continue until its deadline. Reviews never auto-import into RAG.</p>
  </div></details>
}
