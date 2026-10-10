import { useCallback, useEffect, useRef, useState } from 'react'
import { createMockAdapter, createTelemetryAdapter, type AdapterEvent, type TelemetryMode } from '../../telemetry/adapter'
import { defaultMockConfig, type MockConfig } from '../../telemetry/mock'
import { ingestTelemetry, initialTelemetryState, type TelemetryState } from '../../telemetry/state'
import { MOCK_PRESETS } from '../model/constants'
import { estimateIntervalMs } from '../model/derive'
import { createJournal, recordEvent, type Journal } from '../model/journal'

export type MissionTelemetry = {
  mode: TelemetryMode
  state: TelemetryState
  journal: Journal
  /** Expected frame cadence: mock config interval in MOCK, estimated from accepted fixes in LIVE. */
  intervalMs: number
  configurationError: string
  /** MOCK only. Active mock configuration (env-derived or DEMO preset). */
  mockConfig: MockConfig | null
  /** MOCK only, DEMO: restarts the local mock adapter with a preset and resets Mission Control state. */
  demo: { presetId: string; restart: (presetId: string) => void } | null
  /** Bumps on every adapter event; use as a cheap change signal. */
  version: number
}

type Options = { mode: TelemetryMode; liveUrl?: string; mockConfig?: MockConfig }

/**
 * Owns the telemetry adapter for Mission Control. Uses the EXISTING adapter factory and the
 * EXISTING `ingestTelemetry` reducer unchanged; additionally records the Mission Control journal
 * by diffing reducer state before/after each event.
 */
export function useMissionTelemetry({ mode, liveUrl, mockConfig = defaultMockConfig }: Options): MissionTelemetry {
  const [session, setSession] = useState({ presetId: 'default', key: 0 })
  const [version, setVersion] = useState(0)
  const [configurationError, setConfigurationError] = useState('')
  const store = useRef<{ state: TelemetryState; journal: Journal; config: MockConfig | null } | null>(null)
  if (!store.current) store.current = { state: initialTelemetryState, journal: createJournal(Date.now(), mode), config: mode === 'MOCK' ? mockConfig : null }

  useEffect(() => {
    const config = mode === 'MOCK' ? { ...mockConfig, ...MOCK_PRESETS[session.presetId]?.cfg } : null
    const detail = config
      ? `${session.presetId !== 'default' ? `DEMO preset ${MOCK_PRESETS[session.presetId].label} · ` : ''}LOSS ${config.lossEvery} · DUP ${config.duplicateEvery} · REORDER ${config.reorderEvery} · BLACKOUT @${config.blackoutStartTick} ×${config.blackoutDurationTicks}`
      : liveUrl
    const s = { state: initialTelemetryState, journal: createJournal(Date.now(), mode, detail), config }
    store.current = s
    setConfigurationError('')
    setVersion((v) => v + 1)
    const emit = (event: AdapterEvent) => {
      const prev = s.state
      const next = ingestTelemetry(prev, event)
      s.state = next
      const interval = s.config ? s.config.intervalMs : estimateIntervalMs(s.journal.trail)
      recordEvent(s.journal, prev, next, event, Date.now(), interval)
      setVersion((v) => v + 1)
    }
    let stop = () => {}
    try {
      const adapter = config ? createMockAdapter(config) : createTelemetryAdapter(mode, { liveUrl })
      stop = adapter.start(emit)
    } catch (error) {
      setConfigurationError(error instanceof Error ? error.message : String(error))
      emit({ type: 'status', status: 'disconnected' })
    }
    return () => stop()
  }, [mode, liveUrl, mockConfig, session])

  const restart = useCallback((presetId: string) => setSession((s) => ({ presetId, key: s.key + 1 })), [])
  const s = store.current as NonNullable<typeof store.current>
  return {
    mode,
    state: s.state,
    journal: s.journal,
    intervalMs: s.config ? s.config.intervalMs : estimateIntervalMs(s.journal.trail),
    configurationError,
    mockConfig: s.config,
    demo: mode === 'MOCK' ? { presetId: session.presetId, restart } : null,
    version,
  }
}
