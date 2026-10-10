import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createMockAdapter, type AdapterEvent } from '../../telemetry/adapter'
import { buildMockTimeline, defaultMockConfig, type MockConfig } from '../../telemetry/mock'
import { ingestTelemetry, initialTelemetryState, type TelemetryState } from '../../telemetry/state'
import { deriveComms } from './derive'
import { createJournal, recordEvent, type Journal } from './journal'
import { outageBanner } from './presenters'

const startMs = Date.parse('2026-10-10T12:00:00.000Z')

function run(config: MockConfig) {
  const box: { state: TelemetryState; journal: Journal; hazardsAtBlackout: number | null; leaked: boolean } = {
    state: initialTelemetryState, journal: createJournal(Date.now(), 'MOCK'), hazardsAtBlackout: null, leaked: false,
  }
  const stop = createMockAdapter(config, () => startMs).start((event: AdapterEvent) => {
    const prev = box.state
    const next = ingestTelemetry(prev, event)
    box.state = next
    recordEvent(box.journal, prev, next, event, Date.now(), config.intervalMs)
    if (next.transportStatus === 'disconnected') {
      if (box.hazardsAtBlackout == null) box.hazardsAtBlackout = Object.keys(next.hazards).length
      else if (Object.keys(next.hazards).length !== box.hazardsAtBlackout) box.leaked = true
    } else box.hazardsAtBlackout = null
  })
  return { box, stop }
}

describe('Mission Control journal over the default mock schedule', () => {
  beforeEach(() => { vi.useFakeTimers(); vi.setSystemTime(startMs) })
  afterEach(() => vi.useRealTimers())

  it('is NOMINAL before the blackout, BLACKOUT during it, RECOVERY after it', () => {
    const { box, stop } = run(defaultMockConfig)
    vi.advanceTimersByTime(15_000)
    expect(deriveComms(box.state, box.journal, Date.now() + 500, 1000).posture).toBe('NOMINAL')
    vi.advanceTimersByTime(7_000) // tick 22: inside blackout (ticks 20–24)
    expect(box.state.transportStatus).toBe('disconnected')
    expect(deriveComms(box.state, box.journal, Date.now() + 500, 1000).posture).toBe('BLACKOUT')
    vi.advanceTimersByTime(3_000) // tick 25: transport restored
    expect(deriveComms(box.state, box.journal, Date.now() + 500, 1000).posture).toBe('RECOVERY')
    stop()
  })

  it('adds no hazards while the transport is disconnected', () => {
    const { box, stop } = run(defaultMockConfig)
    vi.advanceTimersByTime(40_000)
    expect(box.leaked).toBe(false)
    stop()
  })

  it('tallies the recovery from reducer outcomes only', () => {
    const { box, stop } = run(defaultMockConfig)
    vi.advanceTimersByTime(26_000) // through tick 26
    const r = box.journal.recovery
    expect(r).not.toBeNull()
    expect(r!.outageMs).toBe(5000)
    // tick 25 delivers seq 20 (captured tick 19, deferred by the blackout); tick 26 delivers seq 26
    expect(r!.frames).toBe(2)
    expect(r!.delayed).toBe(1)
    expect(r!.gap).toBe(5)
    expect(box.journal.spans).toHaveLength(1)
    expect(box.journal.spans[0].to! - box.journal.spans[0].from).toBe(5000)
    stop()
  })

  it('marks trail segments after skipped sequences and keeps counters equal to the reducer', () => {
    const { box, stop } = run(defaultMockConfig)
    vi.advanceTimersByTime(30_000)
    const gapSum = box.journal.trail.reduce((s, p) => s + p.gap, 0)
    expect(gapSum).toBe(box.state.sequenceGaps)
    expect(box.journal.trail).toHaveLength(box.state.accepted)
    stop()
  })
})

describe('LIVE station transport and rover radio reports', () => {
  it('marks connected transport with silent telemetry as stale without claiming radio blackout', () => {
    const j = createJournal(startMs, 'LIVE')
    const connected = ingestTelemetry(initialTelemetryState, { type: 'status', status: 'connected' })
    recordEvent(j, initialTelemetryState, connected, { type: 'status', status: 'connected' }, startMs, 1000)
    const frame = buildMockTimeline(defaultMockConfig, startMs).generated[0]
    const packet: AdapterEvent = { type: 'packet', raw: frame, receivedAt: new Date(startMs).toISOString() }
    const accepted = ingestTelemetry(connected, packet)
    recordEvent(j, connected, accepted, packet, startMs, 1000)
    const d = deriveComms(accepted, j, startMs + 6000, 1000)
    expect(d.posture).toBe('STALE')
    expect(outageBanner(d, j, startMs + 6000)?.title).toBe('No fresh telemetry')
    expect(j.events.every((event) => !event.msg.includes('radio blackout'))).toBe(true)
  })

  it('keeps last-reported rover link separate from a disconnected WebSocket', () => {
    const j = createJournal(startMs, 'LIVE')
    const connectedEvent: AdapterEvent = { type: 'status', status: 'connected' }
    const connected = ingestTelemetry(initialTelemetryState, connectedEvent)
    recordEvent(j, initialTelemetryState, connected, connectedEvent, startMs, 1000)
    const frame = buildMockTimeline(defaultMockConfig, startMs).generated[0]
    const packet: AdapterEvent = { type: 'packet', raw: frame, receivedAt: new Date(startMs).toISOString() }
    const accepted = ingestTelemetry(connected, packet)
    recordEvent(j, connected, accepted, packet, startMs, 1000)
    const downEvent: AdapterEvent = { type: 'status', status: 'disconnected' }
    const down = ingestTelemetry(accepted, downEvent)
    recordEvent(j, accepted, down, downEvent, startMs + 1000, 1000)
    const d = deriveComms(down, j, startMs + 2000, 1000)
    expect(d.posture).toBe('TRANSPORT_DOWN')
    expect(d.frame?.link.status).toBe('connected')
    expect(outageBanner(d, j, startMs + 2000)?.line2).toContain('radio state is unknown')
    expect(j.events[0].tag).toBe('STATION DOWN')
  })
})
