import { describe, expect, it, vi } from 'vitest'
import { createLiveAdapter, createMockAdapter, type AdapterEvent } from './adapter'
import { buildMockTimeline, defaultMockConfig } from './mock'
import { ingestTelemetry, initialTelemetryState } from './state'

const startMs = Date.parse('2026-10-10T12:00:00.000Z')
const config = { ...defaultMockConfig, intervalMs: 1000, totalTicks: 20, latencyTicks: 2, lossEvery: 7, duplicateEvery: 5, reorderEvery: 4, blackoutStartTick: 10, blackoutDurationTicks: 3 }

describe('deterministic mock telemetry', () => {
  it('repeats the same rover generation and delivery schedule', () => {
    expect(buildMockTimeline(config, startMs)).toEqual(buildMockTimeline(config, startMs))
    expect(buildMockTimeline({ ...config, seed: 8 }, startMs).generated[0].roverPosition).not.toEqual(buildMockTimeline(config, startMs).generated[0].roverPosition)
  })

  it('keeps captured, received, and blackout times distinct', () => {
    const timeline = buildMockTimeline(config, startMs)
    expect(timeline.generated).toHaveLength(20)
    expect(timeline.generated[10].link.status).toBe('disconnected')
    expect(timeline.deliveries.some((delivery) => delivery.deliveryTick >= 10 && delivery.deliveryTick < 13)).toBe(false)
    expect(timeline.deliveries.some((delivery) => delivery.deliveryTick >= 13)).toBe(true)
    expect(timeline.deliveries[0].deliveryTick).toBe(2)
    expect(timeline.generated[0].capturedAt).toBe('2026-10-10T12:00:00.000Z')
    expect(timeline.generated[6].link.packetsLost).toBe(1)
  })

  it('emits blackout and recovery and the same packet event shape as live', () => {
    vi.useFakeTimers()
    try {
      const events: AdapterEvent[] = []
      const stop = createMockAdapter(config, () => startMs).start((event) => events.push(event))
      vi.advanceTimersByTime(15_000)
      stop()
      expect(events.filter((event) => event.type === 'status').map((event) => event.type === 'status' && event.status)).toEqual(['connecting', 'connected', 'disconnected', 'connected'])
      const packets = events.filter((event) => event.type === 'packet')
      expect(packets.some((event) => event.type === 'packet' && event.receivedAt === '2026-10-10T12:00:02.000Z')).toBe(true)
    } finally { vi.useRealTimers() }
  })
})

describe('common ingestion', () => {
  const timeline = buildMockTimeline(config, startMs)
  const packet = (sequence: number, receivedTick: number): AdapterEvent => ({ type: 'packet', raw: JSON.stringify(timeline.generated[sequence - 1]), receivedAt: new Date(startMs + receivedTick * 1000).toISOString() })

  it('rejects duplicate and older packets without rewinding state', () => {
    let state = ingestTelemetry(initialTelemetryState, packet(1, 2))
    state = ingestTelemetry(state, packet(3, 4))
    state = ingestTelemetry(state, packet(3, 5))
    state = ingestTelemetry(state, packet(2, 6))
    expect(state.latest?.frame.sequence).toBe(3)
    expect(state.latest?.receivedAt).toBe('2026-10-10T12:00:04.000Z')
    expect({ received: state.received, accepted: state.accepted, duplicates: state.duplicates, outOfOrder: state.outOfOrder, sequenceGaps: state.sequenceGaps }).toEqual({ received: 4, accepted: 2, duplicates: 1, outOfOrder: 1, sequenceGaps: 1 })
  })

  it('counts invalid JSON and contract violations', () => {
    const badJson = ingestTelemetry(initialTelemetryState, { type: 'packet', raw: '{', receivedAt: new Date(startMs).toISOString() })
    const badFrame = ingestTelemetry(badJson, { type: 'packet', raw: { ...timeline.generated[0], schemaVersion: 2 }, receivedAt: new Date(startMs).toISOString() })
    expect(badFrame.invalid).toBe(2)
    expect(badFrame.latest).toBeNull()
  })

  it('updates transport status independently of last rover frame', () => {
    const state = ingestTelemetry(ingestTelemetry(initialTelemetryState, packet(1, 2)), { type: 'status', status: 'disconnected' })
    expect(state.transportStatus).toBe('disconnected')
    expect(state.latest?.frame.link.status).toBe('connected')
  })
})

describe('live adapter', () => {
  it('forwards raw wire data for the common parser and tracks connection', () => {
    class FakeSocket {
      static instance: FakeSocket
      onopen: (() => void) | null = null
      onclose: (() => void) | null = null
      onerror: (() => void) | null = null
      onmessage: ((event: { data: string }) => void) | null = null
      constructor(public url: string) { FakeSocket.instance = this }
      close() { this.onclose?.() }
    }
    const events: AdapterEvent[] = []
    const stop = createLiveAdapter('ws://localhost:8765/telemetry', FakeSocket as unknown as typeof WebSocket).start((event) => events.push(event))
    FakeSocket.instance.onopen?.()
    FakeSocket.instance.onmessage?.({ data: JSON.stringify(buildMockTimeline(config, startMs).generated[0]) })
    stop()
    expect(FakeSocket.instance.url).toBe('ws://localhost:8765/telemetry')
    expect(events.map((event) => event.type)).toEqual(['status', 'status', 'packet', 'status'])
    const packetEvent = events[2]
    if (packetEvent.type !== 'packet') throw new Error('expected packet')
    expect(ingestTelemetry(initialTelemetryState, packetEvent).accepted).toBe(1)
  })
})
