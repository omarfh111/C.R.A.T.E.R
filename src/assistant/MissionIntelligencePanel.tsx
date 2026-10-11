import { useEffect, useRef, useState, type ReactNode } from 'react'
import { AssistantError, createAssistantClient, type AssistantAnswer, type AssistantErrorCode, type AssistantHealth } from '../../integrations/m3-assistant-client'
import type { MissionIntelligence } from './missionIntelligence'
import './mission-intelligence.css'

type Phase = 'disabled' | 'checking' | 'ready' | 'loading' | 'answered' | 'insufficient_evidence' | AssistantErrorCode
const labels: Record<Phase, string> = {
  disabled: 'OFFLINE BY DEFAULT', checking: 'CHECKING SERVICE', ready: 'HTTP READY', loading: 'GENERATING', answered: 'UNVERIFIED EXPLANATION',
  insufficient_evidence: 'INSUFFICIENT EVIDENCE', unavailable: 'UNAVAILABLE', busy: 'BUSY', timeout: 'TIMED OUT', failed: 'FAILED', invalid_response: 'INVALID RESPONSE', cancelled: 'CANCELLED', invalid_request: 'INVALID REQUEST',
}
export function MissionIntelligencePanel({ intelligence, children }: { intelligence: MissionIntelligence; children?: ReactNode }) {
  const [open, setOpen] = useState(true)
  const [baseUrl, setBaseUrl] = useState<string>(import.meta.env.VITE_ASSISTANT_URL || 'http://127.0.0.1:8766')
  const [question, setQuestion] = useState('How does NASA Perseverance use cameras during autonomous driving?')
  const [phase, setPhase] = useState<Phase>('disabled')
  const [health, setHealth] = useState<AssistantHealth | null>(null)
  const [message, setMessage] = useState('Optional local science context. Connect only after starting the assistant sidecar.')
  const [answer, setAnswer] = useState<AssistantAnswer | null>(null)
  const active = useRef<AbortController | null>(null)
  const requestId = useRef(0)
  const client = useRef<ReturnType<typeof createAssistantClient> | null>(null)
  useEffect(() => () => { requestId.current++; active.current?.abort() }, [])
  const waiting = phase === 'checking' || phase === 'loading'
  function report(error: unknown) {
    const e = error instanceof AssistantError ? error : new AssistantError('failed', 'The local assistant request failed.')
    setPhase(e.code); setMessage(e.message)
    if (e.code === 'timeout' || e.code === 'cancelled' || e.code === 'unavailable') setHealth(null)
  }
  async function connect() {
    const id = ++requestId.current
    active.current?.abort(); const controller = new AbortController(); active.current = controller
    setHealth(null); setAnswer(null); setPhase('checking'); setMessage('Checking HTTP service and cached model prerequisites. No generation is requested.')
    try {
      client.current = createAssistantClient({ baseUrl })
      const value = await client.current.health(controller.signal)
      if (requestId.current !== id) return
      setHealth(value)
      if (value.modelStatus === 'unavailable') { setPhase('unavailable'); setMessage('HTTP is ready, but the configured Ollama models are unavailable. Start Ollama and restart the sidecar after checking installed models.') }
      else if (value.inferenceState === 'timeout_requires_restart') { setPhase('timeout'); setMessage('A prior inference exceeded its deadline. Verify or unload Ollama, then restart the sidecar and reconnect before asking again.') }
      else if (value.inferenceState === 'capture_blocked') { setPhase('busy'); setMessage('Live M1 capture is active. Science generation is blocked to preserve perception; recheck the service after capture finishes.') }
      else if (value.busy) { setPhase('busy'); setMessage('HTTP is ready. A generation is already running; retry when it completes.') }
      else { setPhase('ready'); setMessage(`${value.indexedChunks} indexed passages. Model prerequisites ${value.modelStatus === 'available' ? 'found' : 'not checked'}; HTTP readiness does not certify a loaded model or a successful answer.`) }
    } catch (error) { if (requestId.current === id) report(error) }
  }
  function disconnect() {
    requestId.current++; active.current?.abort(); active.current = null; client.current = null
    setPhase('disabled'); setHealth(null); setAnswer(null)
    setMessage('Disconnected. Cancelling a browser request does not guarantee that backend inference has stopped.')
  }
  async function ask() {
    if (!client.current || !health || waiting) return
    const id = ++requestId.current, controller = new AbortController(); active.current = controller
    setAnswer(null); setPhase('loading'); setMessage('Retrieving curated references and generating a local explanation. Telemetry reception continues independently.')
    try {
      // Only the operator question is sent. Accepted mission state is never sent to or updated by the model.
      const result = await client.current.ask(question.trim(), 3, controller.signal)
      if (requestId.current !== id) return
      setAnswer(result); setPhase(result.status)
      setMessage(result.status === 'answered' ? 'Citation format passed validation; factual correctness still requires review.' : 'The selected evidence does not support an answer. No mission measurement has been added.')
    } catch (error) { if (requestId.current === id) report(error) }
  }
  return (
    <section className="mi" aria-label="Mission Intelligence">
      <button className="mi__heading" type="button" aria-expanded={open} aria-controls="mission-intelligence-body" onClick={() => setOpen(v => !v)}>
        <span><span className="mc-kicker">MISSION INTELLIGENCE</span><span className="mi__subtitle">{intelligence.summary}</span></span>
        <span className="mi__caret" aria-hidden="true">{open ? '−' : '+'}</span>
      </button>
      {open && <div id="mission-intelligence-body" className="mi__body">
        <div className="mi__label"><span className={`mi__dot${intelligence.stale ? ' mi__dot--aged' : ''}`} /><span>ACCEPTED TELEMETRY · NO LLM</span></div>
        {intelligence.facts.length === 0 ? <p className="mi__note">{intelligence.summary}</p> : <dl className="mi__facts">{intelligence.facts.map(f => <div key={f.label}><dt>{f.label}</dt><dd>{f.text}</dd></div>)}</dl>}
        <details className="mi__integrity"><summary>Evidence boundaries</summary><p>{intelligence.limitations}</p></details>
        {children}
        <details className="mi__science">
          <summary><span>LOCAL AI · SCIENCE CONTEXT</span><span className="mi__optional">OPTIONAL</span></summary>
          <div className="mi__science-body">
            <p className="mi__note">Curated NASA/ESA reference summaries. Generated explanations are unverified and cannot create observations or control the rover. Ask after capture if model use competes with perception.</p>
            <label className="mi__field">Local service URL<input aria-label="Local assistant service URL" type="url" value={baseUrl} disabled={health !== null || waiting} onChange={e => setBaseUrl(e.target.value)} spellCheck={false} /></label>
            <div className="mi__actions"><button type="button" onClick={connect} disabled={waiting}>{health ? 'RECHECK SERVICE' : 'CONNECT LOCAL AI'}</button>{(health || waiting) && <button type="button" onClick={disconnect}>DISCONNECT</button>}</div>
            <div className={`mi__status mi__status--${phase}`} role="status" aria-live="polite"><strong>{labels[phase]}</strong><span>{message}</span></div>
            {health && <p className="mi__model">{health.llm}<br />{health.embedding}</p>}
            <form onSubmit={e => { e.preventDefault(); void ask() }}>
              <label className="mi__field">Science question<textarea aria-label="Science question" rows={3} maxLength={2000} value={question} onChange={e => setQuestion(e.target.value)} disabled={waiting} /></label>
              <div className="mi__actions"><button type="submit" disabled={!health || health.modelStatus === 'unavailable' || ['timeout_requires_restart', 'capture_blocked'].includes(health.inferenceState ?? '') || waiting || !question.trim()}>ASK REFERENCES</button>{phase === 'loading' && <button type="button" onClick={() => active.current?.abort()}>CANCEL REQUEST</button>}</div>
            </form>
            {answer && <div className="mi__answer">
              <span className="mi__answer-label">UNVERIFIED GENERATED TEXT · SEPARATE FROM MISSION FACTS</span>
              <p className="mi__answer-text">{answer.answer}</p>
              <details className="mi__sources" open><summary>Evidence · {answer.sources.length} passage{answer.sources.length === 1 ? '' : 's'}</summary>{answer.sources.map(s => <details className="mi__source" key={s.sourceId}>
                <summary>[{s.sourceId}] {s.path.split(/[\\/]/).pop()} · lines {s.lineStart}–{s.lineEnd}{answer.citedSourceIds.includes(s.sourceId) ? ' · CITED' : ''}</summary>
                <blockquote>{s.text}</blockquote>
                {s.sourceUrl && <a href={s.sourceUrl} target="_blank" rel="noopener noreferrer">Open source reference ↗</a>}
                <p className="mi__source-meta">Summary metadata verified: {s.verifiedOn ?? 'not supplied'}<br />SHA-256 {s.digest}</p>
              </details>)}</details>
              <p className="mi__limitations">{answer.limitations}</p>
            </div>}
            <p className="mi__note mi__footnote">A cancelled or timed-out request may keep running on the server until its deadline. Citation checks establish source identity, not semantic truth. No image understanding is performed.</p>
          </div>
        </details>
      </div>}
    </section>
  )
}
