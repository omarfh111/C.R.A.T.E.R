import React, { useEffect, useReducer, useState } from 'react'
import ReactDOM from 'react-dom/client'
import '@fontsource/space-grotesk/300.css'
import '@fontsource/space-grotesk/400.css'
import '@fontsource/space-grotesk/600.css'
import '@fontsource/ibm-plex-mono/400.css'
import '@fontsource/ibm-plex-mono/500.css'
import { LunarIntro } from './intro/LunarIntro'
import { useIntroPlayback } from './intro/useIntroPlayback'
import { createTelemetryAdapter, type TelemetryMode } from './telemetry/adapter'
import { defaultMockConfig, type MockConfig } from './telemetry/mock'
import { ingestTelemetry, initialTelemetryState } from './telemetry/state'
import './style.css'

const mode: TelemetryMode = import.meta.env.VITE_TELEMETRY_MODE === 'LIVE' ? 'LIVE' : 'MOCK'

function mockConfigFromEnv(): MockConfig {
  const integer = (name: string, fallback: number) => {
    const raw = import.meta.env[name]
    const value = Number(raw)
    return raw !== undefined && Number.isInteger(value) && value >= 0 ? value : fallback
  }
  return {
    ...defaultMockConfig,
    intervalMs: Math.max(100, integer('VITE_MOCK_INTERVAL_MS', defaultMockConfig.intervalMs)),
    seed: integer('VITE_MOCK_SEED', defaultMockConfig.seed),
    totalTicks: integer('VITE_MOCK_TOTAL_TICKS', defaultMockConfig.totalTicks),
    latencyTicks: integer('VITE_MOCK_LATENCY_TICKS', defaultMockConfig.latencyTicks),
    lossEvery: integer('VITE_MOCK_LOSS_EVERY', defaultMockConfig.lossEvery),
    duplicateEvery: integer('VITE_MOCK_DUPLICATE_EVERY', defaultMockConfig.duplicateEvery),
    reorderEvery: integer('VITE_MOCK_REORDER_EVERY', defaultMockConfig.reorderEvery),
    blackoutStartTick: integer('VITE_MOCK_BLACKOUT_START_TICK', defaultMockConfig.blackoutStartTick),
    blackoutDurationTicks: integer('VITE_MOCK_BLACKOUT_DURATION_TICKS', defaultMockConfig.blackoutDurationTicks),
  }
}

function App() {
  const [state, dispatch] = useReducer(ingestTelemetry, initialTelemetryState)
  const [now, setNow] = useState(Date.now())
  const [configurationError, setConfigurationError] = useState('')
  const { introVisible, introRun, handoffStarted, startHandoff, completeIntro, replayIntro } = useIntroPlayback()

  useEffect(() => {
    const clock = setInterval(() => setNow(Date.now()), 1000)
    let stop = () => {}
    try {
      stop = createTelemetryAdapter(mode, {
        liveUrl: import.meta.env.VITE_TELEMETRY_WS_URL,
        mockConfig: mockConfigFromEnv(),
      }).start(dispatch)
    } catch (error) {
      setConfigurationError(error instanceof Error ? error.message : String(error))
      dispatch({ type: 'status', status: 'disconnected' })
    }
    return () => { stop(); clearInterval(clock) }
  }, [])

  const lastReceipt = state.latest?.receivedAt
  const stale = lastReceipt !== undefined && now - Date.parse(lastReceipt) > 5000
  const connection = state.transportStatus === 'connected' && stale ? 'stale' : state.transportStatus
  const frame = state.latest?.frame
  const hazards = Object.entries(state.hazards).slice(-6).reverse()

  return <><main inert={introVisible} aria-hidden={introVisible} className={`dashboard-shell ${introVisible && !handoffStarted ? 'dashboard-shell--intro-active' : ''} mx-auto max-w-4xl space-y-6 p-6 text-slate-100`}>
    <header className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-700 pb-4">
      <div><p className="dashboard-kicker">LUNAR SURFACE RECONNAISSANCE</p>
        <h1 className="text-2xl font-semibold">C.R.A.T.E.R. <span className="text-cyan-200">Mission Control</span></h1>
        <p className="mt-2 text-sm text-slate-400">Telemetry foundation · local ENU coordinates in meters</p></div>
      <button className="dashboard-replay" type="button" onClick={replayIntro}>↺ REPLAY INTRO</button>
    </header>
    <section className="flex flex-wrap gap-3 text-sm" aria-label="Source and connection">
      <span className="rounded bg-slate-800 px-3 py-2">Source: <strong>{mode}</strong></span>
      <span className="rounded bg-slate-800 px-3 py-2" role="status">Connection: <strong>{connection}</strong></span>
      <span className="rounded bg-slate-800 px-3 py-2">Schema: <strong>v1</strong></span>
    </section>
    {configurationError && <p className="rounded border border-rose-500 p-3 text-rose-300">{configurationError}</p>}
    <section className="grid gap-4 md:grid-cols-2">
      <div className="rounded border border-slate-700 bg-slate-900 p-4">
        <h2 className="mb-3 font-semibold">Latest accepted rover frame</h2>
        {frame ? <dl className="grid grid-cols-2 gap-2 text-sm">
          <dt className="text-slate-400">Rover / sequence</dt><dd>{frame.roverId} / {frame.sequence}</dd>
          <dt className="text-slate-400">Position (E, N, U)</dt><dd>{frame.roverPosition.xM}, {frame.roverPosition.yM}, {frame.roverPosition.zM} m</dd>
          <dt className="text-slate-400">Position uncertainty</dt><dd>{frame.positionUncertaintyRadiusM} m</dd>
          <dt className="text-slate-400">Rover link</dt><dd>{frame.link.status}</dd>
          <dt className="text-slate-400">Captured by rover</dt><dd>{frame.capturedAt}</dd>
          <dt className="text-slate-400">Received here</dt><dd>{lastReceipt}</dd>
        </dl> : <p className="text-sm text-slate-400">Waiting for a valid frame…</p>}
      </div>
      <div className="rounded border border-slate-700 bg-slate-900 p-4">
        <h2 className="mb-3 font-semibold">Packet accounting</h2>
        <dl className="grid grid-cols-2 gap-2 text-sm">
          <dt className="text-slate-400">Rover reported sent / lost</dt><dd>{frame ? `${frame.link.packetsSent} / ${frame.link.packetsLost}` : '—'}</dd>
          <dt className="text-slate-400">Mission Control received</dt><dd>{state.received}</dd>
          <dt className="text-slate-400">Accepted / invalid</dt><dd>{state.accepted} / {state.invalid}</dd>
          <dt className="text-slate-400">Duplicate / older</dt><dd>{state.duplicates} / {state.outOfOrder}</dd>
          <dt className="text-slate-400">Sequence gaps</dt><dd>{state.sequenceGaps}</dd>
        </dl>
      </div>
    </section>
    <section className="rounded border border-slate-700 bg-slate-900 p-4">
      <h2 className="mb-3 font-semibold">Observed hazards ({Object.keys(state.hazards).length})</h2>
      {hazards.length ? <ul className="space-y-2 text-sm">{hazards.map(([key, hazard]) => <li key={key} className="flex flex-wrap justify-between gap-2 border-t border-slate-800 pt-2"><span>{hazard.id} · {hazard.type}</span><span>{hazard.position.xM}, {hazard.position.yM} m · confidence {Math.round(hazard.confidence * 100)}%</span></li>)}</ul> : <p className="text-sm text-slate-400">No hazard observations received yet.</p>}
    </section>
  </main>{introVisible && <LunarIntro key={introRun} replay={introRun > 0} onHandoffStart={startHandoff} onComplete={completeIntro} />}</>
}

const root = ReactDOM.createRoot(document.getElementById('root')!)
root.render(<React.StrictMode><App /></React.StrictMode>)
import.meta.hot?.dispose(() => root.unmount())
