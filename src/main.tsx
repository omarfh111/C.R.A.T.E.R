// INTEGRATION TARGET: replaces src/main.tsx on feat/mission-control.
// Unchanged from the current file: fonts, intro wiring, env-driven mock config, MOCK/LIVE mode selection.
// Changed: the Phase 1 dashboard body is replaced by <MissionControl>, and adapter/reducer wiring moves
// into useMissionTelemetry (which calls the SAME createTelemetryAdapter / createMockAdapter / ingestTelemetry).
import React from 'react'
import ReactDOM from 'react-dom/client'
import '@fontsource/space-grotesk/300.css'
import '@fontsource/space-grotesk/400.css'
import '@fontsource/space-grotesk/500.css' // NEW weight used by Mission Control (same installed package)
import '@fontsource/space-grotesk/600.css'
import '@fontsource/ibm-plex-mono/400.css'
import '@fontsource/ibm-plex-mono/500.css'
import '@fontsource/ibm-plex-mono/600.css' // NEW weight used by Mission Control (same installed package)
import { LunarIntro } from './intro/LunarIntro'
import { useIntroPlayback } from './intro/useIntroPlayback'
import type { TelemetryMode } from './telemetry/adapter'
import { defaultMockConfig, type MockConfig } from './telemetry/mock'
import { MissionControl, useMissionTelemetry } from './mission-control'
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

// Module-level so the object identity is stable (the hook restarts the adapter when it changes).
const mockConfig = mockConfigFromEnv()

function App() {
  const telemetry = useMissionTelemetry({ mode, liveUrl: import.meta.env.VITE_TELEMETRY_WS_URL, mockConfig })
  const { introVisible, introRun, handoffStarted, startHandoff, completeIntro, replayIntro } = useIntroPlayback()

  return <>
    <MissionControl
      telemetry={telemetry}
      onReplayIntro={replayIntro}
      introActive={introVisible && !handoffStarted}
      inert={introVisible}
      className={`dashboard-shell ${introVisible && !handoffStarted ? 'dashboard-shell--intro-active' : ''}`}
    />
    {introVisible && <LunarIntro key={introRun} replay={introRun > 0} onHandoffStart={startHandoff} onComplete={completeIntro} />}
  </>
}

const root = ReactDOM.createRoot(document.getElementById('root')!)
root.render(<React.StrictMode><App /></React.StrictMode>)
import.meta.hot?.dispose(() => root.unmount())
