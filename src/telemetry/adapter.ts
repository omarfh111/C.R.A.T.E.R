import { buildMockTimeline, defaultMockConfig, type MockConfig } from './mock'

export type TransportStatus = 'connecting' | 'connected' | 'disconnected'
export type AdapterEvent =
  | { type: 'status'; status: TransportStatus }
  | { type: 'packet'; raw: unknown; receivedAt: string }

export interface TelemetryAdapter {
  start(emit: (event: AdapterEvent) => void): () => void
}

export function createMockAdapter(config: MockConfig = defaultMockConfig, now: () => number = Date.now): TelemetryAdapter {
  return {
    start(emit) {
      const startMs = now()
      const timeline = buildMockTimeline(config, startMs)
      let tick = 0
      let deliveryIndex = 0
      let connected = false
      const step = () => {
        const blackout = tick >= config.blackoutStartTick && tick < config.blackoutStartTick + config.blackoutDurationTicks
        if (connected === blackout) {
          connected = !blackout
          emit({ type: 'status', status: connected ? 'connected' : 'disconnected' })
        }
        while (deliveryIndex < timeline.deliveries.length && timeline.deliveries[deliveryIndex].deliveryTick === tick) {
          const delivery = timeline.deliveries[deliveryIndex++]
          emit({ type: 'packet', raw: delivery.frame, receivedAt: new Date(startMs + tick * config.intervalMs).toISOString() })
        }
        tick++
        if (tick > config.totalTicks + config.latencyTicks + 3) {
          clearInterval(timer)
          emit({ type: 'status', status: 'disconnected' })
        }
      }
      emit({ type: 'status', status: 'connecting' })
      const timer = setInterval(step, config.intervalMs)
      step()
      return () => clearInterval(timer)
    },
  }
}

export function createLiveAdapter(url: string, WebSocketClass: typeof WebSocket = WebSocket): TelemetryAdapter {
  return {
    start(emit) {
      emit({ type: 'status', status: 'connecting' })
      const socket = new WebSocketClass(url)
      socket.onopen = () => emit({ type: 'status', status: 'connected' })
      socket.onclose = () => emit({ type: 'status', status: 'disconnected' })
      socket.onerror = () => emit({ type: 'status', status: 'disconnected' })
      socket.onmessage = (message) => emit({ type: 'packet', raw: message.data, receivedAt: new Date().toISOString() })
      return () => socket.close()
    },
  }
}

export type TelemetryMode = 'MOCK' | 'LIVE'

export function createTelemetryAdapter(mode: TelemetryMode, options: { liveUrl?: string; mockConfig?: MockConfig } = {}): TelemetryAdapter {
  if (mode === 'MOCK') return createMockAdapter(options.mockConfig)
  if (!options.liveUrl) throw new Error('VITE_TELEMETRY_WS_URL is required in LIVE mode')
  return createLiveAdapter(options.liveUrl)
}
