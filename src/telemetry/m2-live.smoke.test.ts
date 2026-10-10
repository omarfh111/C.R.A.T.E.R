import { expect, it } from 'vitest'
import { telemetryFrameSchema, type TelemetryFrame } from './contract'

// Opt in only while M2's local bridge is running. This uses its real WebSocket output;
// the normal offline suite never depends on another process.
it.skipIf(process.env.CRATER_M2_LIVE_SMOKE !== '1')('accepts actual M2-decoded canonical v1 frames', async () => {
  const url = process.env.CRATER_M2_WS_URL ?? 'ws://127.0.0.1:8765/telemetry'
  const frames = await new Promise<TelemetryFrame[]>((resolve, reject) => {
    const socket = new WebSocket(url)
    const received: TelemetryFrame[] = []
    const timeout = setTimeout(() => { socket.close(); reject(new Error('M2 sent fewer than three frames within 30 s')) }, 30_000)
    socket.onmessage = (event) => {
      try {
        const frame = telemetryFrameSchema.parse(JSON.parse(String(event.data)))
        received.push(frame)
        if (received.length === 3) {
          clearTimeout(timeout)
          socket.close()
          resolve(received)
        }
      } catch (error) { clearTimeout(timeout); socket.close(); reject(error) }
    }
    socket.onerror = () => { clearTimeout(timeout); reject(new Error(`M2 WebSocket unavailable at ${url}`)) }
    socket.onclose = () => {
      if (received.length < 3) { clearTimeout(timeout); reject(new Error('M2 closed before three frames')) }
    }
  })
  expect(frames.every((frame) => frame.roverPosition.frameId === 'LOCAL_ENU_V1')).toBe(true)
  expect(frames.every((frame) => Number.isFinite(Date.parse(frame.capturedAt)))).toBe(true)
  expect(frames.every((frame) => frame.positionUncertaintyRadiusM >= 0)).toBe(true)
  expect(frames.every((frame) => frame.link.packetsLost <= frame.link.packetsSent)).toBe(true)
  expect(frames.some((frame) => frame.hazards.some((hazard) => hazard.confidence > 0 && hazard.uncertaintyRadiusM > 0))).toBe(true)
  expect(frames[2].sequence).toBeGreaterThan(frames[0].sequence)
})
