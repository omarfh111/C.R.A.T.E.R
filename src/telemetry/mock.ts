import type { TelemetryFrame } from './contract'

export type MockConfig = {
  intervalMs: number
  seed: number
  totalTicks: number
  latencyTicks: number
  lossEvery: number
  duplicateEvery: number
  reorderEvery: number
  blackoutStartTick: number
  blackoutDurationTicks: number
}

export const defaultMockConfig: MockConfig = {
  intervalMs: 1000,
  seed: 7,
  totalTicks: 3600,
  latencyTicks: 1,
  lossEvery: 9,
  duplicateEvery: 13,
  reorderEvery: 11,
  blackoutStartTick: 20,
  blackoutDurationTicks: 5,
}

export type MockDelivery = { deliveryTick: number; frame: TelemetryFrame; duplicate: boolean }
export type MockTimeline = { generated: TelemetryFrame[]; deliveries: MockDelivery[] }

export function buildMockTimeline(config: MockConfig, startMs: number): MockTimeline {
  if (!Number.isInteger(config.totalTicks) || config.totalTicks < 0 || config.intervalMs <= 0 || config.latencyTicks < 0) {
    throw new Error('Invalid mock timing configuration')
  }
  const generated: TelemetryFrame[] = []
  const deliveries: MockDelivery[] = []
  let lost = 0
  for (let tick = 0; tick < config.totalTicks; tick++) {
    const sequence = tick + 1
    const blackout = tick >= config.blackoutStartTick && tick < config.blackoutStartTick + config.blackoutDurationTicks
    const dropped = blackout || (config.lossEvery > 0 && sequence % config.lossEvery === 0)
    if (dropped) lost++
    const capturedAt = new Date(startMs + tick * config.intervalMs).toISOString()
    const phase = (tick + config.seed) / 9
    const xM = Number((tick * 0.36).toFixed(2))
    const yM = Number((Math.sin(phase) * 2).toFixed(2))
    const frame: TelemetryFrame = {
      schemaVersion: 1,
      roverId: 'mock-rover-1',
      sequence,
      capturedAt,
      roverPosition: { frameId: 'LOCAL_ENU_V1', xM, yM, zM: 0 },
      positionUncertaintyRadiusM: 0.25,
      link: { status: blackout ? 'disconnected' : 'connected', packetsSent: sequence, packetsLost: lost },
      hazards: sequence % 5 === 0 ? [{
        id: `hazard-${Math.floor(sequence / 5)}`,
        type: sequence % 10 === 0 ? 'rock' : 'crater',
        position: { frameId: 'LOCAL_ENU_V1', xM: xM + 1.2, yM: yM + 0.8, zM: 0 },
        confidence: 0.82,
        uncertaintyRadiusM: 0.4,
        observedAt: capturedAt,
      }] : [],
    }
    generated.push(frame)
    if (dropped) continue
    let deliveryTick = tick + config.latencyTicks + (config.reorderEvery > 0 && sequence % config.reorderEvery === 0 ? 2 : 0)
    if (deliveryTick >= config.blackoutStartTick && deliveryTick < config.blackoutStartTick + config.blackoutDurationTicks) {
      deliveryTick = config.blackoutStartTick + config.blackoutDurationTicks
    }
    deliveries.push({ deliveryTick, frame, duplicate: false })
    if (config.duplicateEvery > 0 && sequence % config.duplicateEvery === 0) {
      deliveries.push({ deliveryTick: deliveryTick + 1, frame, duplicate: true })
    }
  }
  deliveries.sort((a, b) => a.deliveryTick - b.deliveryTick || a.frame.sequence - b.frame.sequence)
  return { generated, deliveries }
}
