import type { MockConfig } from '../../telemetry/mock'
import type { HazardType, Posture } from './types'

export const MC_COLORS = {
  bg: '#03070c', cyan: '#9bddea', cyanHi: '#c9f3fa', amber: '#f2b54a', red: '#ef5b4c',
  silver: '#c2dce3', text: '#e9f0f3', muted: '#8fa6b2', dim: '#5f7581', kicker: '#86c9d7', steel: '#a5b9c4',
} as const

export const HAZARD_STYLE: Record<HazardType, { color: string; rgb: string; label: string }> = {
  crater: { color: '#f2b54a', rgb: '242,181,74', label: 'CRATER' },
  rock: { color: '#ef5b4c', rgb: '239,91,76', label: 'ROCK' },
  slope: { color: '#f58a5c', rgb: '245,138,92', label: 'SLOPE' },
  unknown: { color: '#b9c6cc', rgb: '185,198,204', label: 'UNKNOWN' },
}
export const HAZARD_TYPES: HazardType[] = ['crater', 'rock', 'slope', 'unknown']

export const POSTURE_STYLE: Record<Posture, { label: string; color: string; rgb: string }> = {
  ACQUIRING: { label: 'ACQUIRING', color: '#a5b9c4', rgb: '165,185,196' },
  NOMINAL: { label: 'NOMINAL', color: '#9bddea', rgb: '155,221,234' },
  DEGRADED: { label: 'DEGRADED', color: '#f2b54a', rgb: '242,181,74' },
  STALE: { label: 'STALE', color: '#f2b54a', rgb: '242,181,74' },
  BLACKOUT: { label: 'BLACKOUT', color: '#ef5b4c', rgb: '239,91,76' },
  TRANSPORT_DOWN: { label: 'TRANSPORT DOWN', color: '#ef5b4c', rgb: '239,91,76' },
  RECOVERY: { label: 'RECOVERY', color: '#c9f3fa', rgb: '201,243,250' },
}

/** Mission Control thresholds. All are UI-side inferences, never rover-reported values. */
export const THRESHOLDS = {
  /** Matches the existing main.tsx rule: transport connected but no accepted frame for 5 s. */
  staleMs: 5000,
  /** Information age beyond this many expected intervals → DEGRADED. */
  degradedIntervals: 3,
  /** Accepted / sequence span over the last 20 accepted frames below this → DEGRADED. */
  minYield: 0.65,
  yieldWindow: 20,
  /** Receipt − capture beyond this many expected intervals → frame marked "late/delayed". */
  lateIntervals: 2.5,
  /** Posture stays RECOVERY for this long after the transport reconnects. */
  recoveryMs: 7000,
  /** Hazard observations older than this are flagged AGED. */
  agedHazardMs: 30000,
  /** Reception strip window. */
  stripWindowMs: 60000,
} as const

/** DEMO-only presets. Each maps 1:1 to VITE_MOCK_* env values; picking one restarts the local mock adapter. */
export const MOCK_PRESETS: Record<string, { label: string; env: string; cfg: Partial<MockConfig> }> = {
  default: { label: 'Default', cfg: {}, env: 'Repo defaults · LOSS 9 · DUP 13 · REORDER 11 · BLACKOUT @20 ×5' },
  early: { label: 'Early blackout', cfg: { blackoutStartTick: 8, blackoutDurationTicks: 8 }, env: 'Defaults with BLACKOUT @8 ×8' },
  lossy: { label: 'Lossy link', cfg: { lossEvery: 3, reorderEvery: 4, duplicateEvery: 5, blackoutStartTick: 30, blackoutDurationTicks: 6 }, env: 'LOSS 3 · REORDER 4 · DUP 5 · BLACKOUT @30 ×6' },
  clean: { label: 'Clean link', cfg: { lossEvery: 0, reorderEvery: 0, duplicateEvery: 0, blackoutDurationTicks: 0 }, env: 'LOSS/DUP/REORDER 0 · no blackout' },
}
