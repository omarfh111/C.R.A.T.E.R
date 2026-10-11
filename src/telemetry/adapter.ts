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
      let stopped = false
      let socket: WebSocket | null = null
      let retryTimer: ReturnType<typeof setTimeout> | null = null
      let failures = 0
      emit({ type: 'status', status: 'connecting' })

      const retry = () => {
        if (stopped || retryTimer) return
        // Retry indefinitely while the view is mounted, with a bounded 8 s delay.
        const delay = Math.min(500 * 2 ** Math.min(failures++, 4), 8000)
        retryTimer = setTimeout(() => { retryTimer = null; connect() }, delay)
      }
      const connect = () => {
        if (stopped || socket) return
        let current: WebSocket
        try { current = new WebSocketClass(url) }
        catch { emit({ type: 'status', status: 'disconnected' }); retry(); return }
        socket = current
        const dropped = () => {
          if (stopped || socket !== current) return
          current.onopen = current.onclose = current.onerror = current.onmessage = null
          socket = null
          emit({ type: 'status', status: 'disconnected' })
          retry()
        }
        current.onopen = () => {
          if (stopped || socket !== current) return
          failures = 0
          emit({ type: 'status', status: 'connected' })
        }
        current.onclose = dropped
        current.onerror = () => { current.close(); dropped() }
        current.onmessage = (message) => {
          if (!stopped && socket === current) emit({ type: 'packet', raw: message.data, receivedAt: new Date().toISOString() })
        }
      }
      connect()
      return () => {
        stopped = true
        if (retryTimer) clearTimeout(retryTimer)
        retryTimer = null
        if (socket) {
          socket.onopen = socket.onclose = socket.onerror = socket.onmessage = null
          socket.close()
          socket = null
        }
      }
    },
  }
}

export type TelemetryMode = 'MOCK' | 'LIVE'

export function createTelemetryAdapter(mode: TelemetryMode, options: { liveUrl?: string; mockConfig?: MockConfig } = {}): TelemetryAdapter {
  if (mode === 'MOCK') return createMockAdapter(options.mockConfig)
  if (!options.liveUrl) throw new Error('VITE_TELEMETRY_WS_URL is required in LIVE mode')
  return createLiveAdapter(options.liveUrl)
}
