import { existsSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

/**
 * Loopback-only test endpoints. Both default away from the demo scripts' 5173/8765 so an
 * interactive `scripts/start-demo.ps1` session and this suite never compete for a port.
 */
function port(name: string, fallback: number): number {
  const raw = process.env[name]
  if (raw === undefined || raw === '') return fallback
  const value = Number(raw)
  if (!Number.isInteger(value) || value < 1024 || value > 65535) {
    throw new Error(`${name} must be an integer from 1024 to 65535; received ${raw}`)
  }
  return value
}

export const WEB_PORT = port('CRATER_E2E_WEB_PORT', 4318)
export const WS_PORT = port('CRATER_E2E_WS_PORT', 8799)
if (WEB_PORT === WS_PORT) throw new Error('CRATER_E2E_WEB_PORT and CRATER_E2E_WS_PORT must differ')

export const BASE_URL = `http://127.0.0.1:${WEB_PORT}`
export const WS_URL = `ws://127.0.0.1:${WS_PORT}/telemetry`

export const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..')
/** Committed calibrated ONNX recording. The suite replays these real predictions; it never invents frames. */
export const OBSERVATIONS = path.join(REPO_ROOT, 'examples/m1-onnx-calibrated/observations.jsonl')
export const E2E_OUTPUT_ROOT = path.join(REPO_ROOT, 'test-results', 'm2-stations')

/** The model-free interpreter that owns `crater_m2`. No ONNX weights, GPU or network are required. */
export function pythonExecutable(): string {
  const explicit = process.env.CRATER_E2E_PYTHON
  if (explicit) return explicit
  const relative = process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python'
  const local = path.join(REPO_ROOT, relative)
  return existsSync(local) ? local : 'python'
}
