import { z } from 'zod'

const finite = z.number().finite()
const nonnegative = finite.nonnegative()
const timestamp = z.iso.datetime({ offset: true })

export const coordinatesSchema = z.strictObject({
  frameId: z.literal('LOCAL_ENU_V1'),
  xM: finite,
  yM: finite,
  zM: finite,
})

export const hazardSchema = z.strictObject({
  id: z.string().min(1),
  type: z.enum(['crater', 'rock', 'slope', 'unknown']),
  position: coordinatesSchema,
  confidence: finite.min(0).max(1),
  uncertaintyRadiusM: nonnegative,
  observedAt: timestamp,
})

export const telemetryFrameSchema = z.strictObject({
  schemaVersion: z.literal(1),
  roverId: z.string().min(1),
  sequence: z.number().int().nonnegative(),
  capturedAt: timestamp,
  roverPosition: coordinatesSchema,
  positionUncertaintyRadiusM: nonnegative,
  link: z.strictObject({
    status: z.enum(['connected', 'degraded', 'disconnected']),
    packetsSent: z.number().int().nonnegative(),
    packetsLost: z.number().int().nonnegative(),
  }).refine((link) => link.packetsLost <= link.packetsSent, 'packetsLost cannot exceed packetsSent'),
  hazards: z.array(hazardSchema),
}).superRefine((frame, context) => {
  for (const [index, hazard] of frame.hazards.entries()) {
    if (Date.parse(hazard.observedAt) > Date.parse(frame.capturedAt)) {
      context.addIssue({ code: 'custom', path: ['hazards', index, 'observedAt'], message: 'observation cannot postdate capture' })
    }
  }
})

export type Coordinates = z.infer<typeof coordinatesSchema>
export type Hazard = z.infer<typeof hazardSchema>
export type TelemetryFrame = z.infer<typeof telemetryFrameSchema>

// receivedAt belongs to Mission Control; it is never part of the rover frame.
export type TelemetryReceipt = { frame: TelemetryFrame; receivedAt: string }

export function parseTelemetryFrame(value: unknown): TelemetryFrame {
  return telemetryFrameSchema.parse(value)
}
