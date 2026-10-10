import { describe, expect, it } from 'vitest'
import { parseTelemetryFrame } from './contract'

const valid = {
  schemaVersion: 1,
  roverId: 'rover-1',
  sequence: 3,
  capturedAt: '2026-10-10T12:00:00.000Z',
  roverPosition: { frameId: 'LOCAL_ENU_V1', xM: 1, yM: 2, zM: 0 },
  positionUncertaintyRadiusM: 0.25,
  link: { status: 'connected', packetsSent: 3, packetsLost: 1 },
  hazards: [{ id: 'h-1', type: 'crater', position: { frameId: 'LOCAL_ENU_V1', xM: 3, yM: 4, zM: -1 }, confidence: 0.8, uncertaintyRadiusM: 0.5, observedAt: '2026-10-10T11:59:59.000Z' }],
}

describe('telemetry contract v1', () => {
  it('accepts a valid frame', () => expect(parseTelemetryFrame(valid).sequence).toBe(3))

  it.each([
    { schemaVersion: 2 },
    { sequence: -1 },
    { capturedAt: '2026-10-10 12:00:00' },
    { roverPosition: { ...valid.roverPosition, frameId: 'GPS' } },
    { link: { ...valid.link, packetsLost: 4 } },
    { hazards: [{ ...valid.hazards[0], confidence: 1.1 }] },
    { hazards: [{ ...valid.hazards[0], observedAt: '2026-10-10T12:00:01.000Z' }] },
    { unexpected: true },
  ])('rejects invalid or unsupported fields: %j', (change) => {
    expect(() => parseTelemetryFrame({ ...valid, ...change })).toThrow()
  })
})
