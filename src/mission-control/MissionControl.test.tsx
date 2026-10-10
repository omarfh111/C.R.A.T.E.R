// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { buildMockTimeline, defaultMockConfig } from '../telemetry/mock'
import { ingestTelemetry, initialTelemetryState } from '../telemetry/state'
import type { AdapterEvent, TelemetryMode } from '../telemetry/adapter'
import { MissionControl } from './MissionControl'
import type { MissionTelemetry } from './hooks/useMissionTelemetry'
import { createJournal, recordEvent } from './model/journal'

vi.mock('./map/TacticalMapView', () => ({ TacticalMap: () => <canvas aria-label="Tactical map" /> }))
vi.mock('./map/receptionStrip', () => ({ drawReceptionStrip: vi.fn() }))
afterEach(cleanup)

function telemetry(mode: TelemetryMode): MissionTelemetry {
  const now = Date.now()
  const j = createJournal(now, mode)
  const connectedEvent: AdapterEvent = { type: 'status', status: 'connected' }
  const connected = ingestTelemetry(initialTelemetryState, connectedEvent)
  recordEvent(j, initialTelemetryState, connected, connectedEvent, now, 1000)
  const frame = buildMockTimeline(defaultMockConfig, now - 4000).generated[4]
  const packet: AdapterEvent = { type: 'packet', raw: frame, receivedAt: new Date(now).toISOString() }
  const state = ingestTelemetry(connected, packet)
  recordEvent(j, connected, state, packet, now, 1000)
  return {
    mode, state, journal: j, intervalMs: 1000, configurationError: '',
    mockConfig: mode === 'MOCK' ? defaultMockConfig : null,
    demo: mode === 'MOCK' ? { presetId: 'default', restart: vi.fn() } : null,
    version: 1,
  }
}

describe('Mission Control accepted telemetry display', () => {
  it('shows accepted hazards in the inspector and keeps DEMO out of LIVE mode', () => {
    render(<MissionControl telemetry={telemetry('LIVE')} />)
    expect(screen.getByText('LIVE')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /^DEMO/ })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /hazard-1 CRATER/i }))
    expect(screen.getByRole('region', { name: 'Hazard inspector' }).textContent).toContain('hazard-1')
    expect(screen.getByRole('region', { name: 'Packet accounting' }).textContent).toContain('ACCEPTED1')
  })

  it('shows mock DEMO controls without a Replay Intro button', () => {
    const source = telemetry('MOCK')
    render(<MissionControl telemetry={source} />)
    expect(screen.getByRole('button', { name: /^DEMO/ })).toBeTruthy()
    expect(screen.queryByRole('button', { name: /REPLAY INTRO/ })).toBeNull()
    expect(source.demo?.restart).not.toHaveBeenCalled()
    expect(screen.getByRole('region', { name: 'Packet accounting' }).textContent).toContain('ACCEPTED1')
  })
})
