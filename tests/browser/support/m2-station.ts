import { spawn, type ChildProcess } from 'node:child_process'
import { closeSync, existsSync, mkdirSync, openSync, readFileSync, rmSync, writeSync } from 'node:fs'
import path from 'node:path'
import { E2E_OUTPUT_ROOT, OBSERVATIONS, pythonExecutable, REPO_ROOT, WS_PORT, WS_URL } from './config'

/** Line M2 prints once the WebSocket bridge is accepting connections. */
const READY_LINE = 'M2 station ready'
const READY_TIMEOUT_MS = 60_000

export type StationOptions = {
  /** Directory-safe name; also used in failure messages and uploaded log paths. */
  label: string
  /** Optional durable incident side channel; canonical telemetry remains unchanged. */
  journalPath?: string
  /** Mission capture window, seconds. */
  durationS: number
  /** Extra seconds M2 may spend draining its retransmission queue. */
  drainS?: number
  fps: number
  /** Per-direction packet loss probability in the simulated lunar radio link. */
  loss: number
  /** `START:END` seconds of simulated radio blackout, or null for an uninterrupted link. */
  blackout: string | null
  queue?: number
  attempts?: number
  /** Seconds M2 waits for a dashboard WebSocket receiver before it starts capturing. */
  waitForClientS?: number
  seed?: number
}

export type DeliveredFrame = {
  schemaVersion: number
  roverId: string
  sequence: number
  capturedAt: string
  roverPosition: { frameId: string; xM: number; yM: number; zM: number }
  positionUncertaintyRadiusM: number
  link: { status: string; packetsSent: number; packetsLost: number }
  hazards: {
    id: string
    type: string
    position: { frameId: string; xM: number; yM: number; zM: number }
    confidence: number
    uncertaintyRadiusM: number
    observedAt: string
  }[]
}

export type M2Station = {
  wsUrl: string
  /** Absolute path of the captured M2 stdout/stderr log; uploaded as a CI artifact on failure. */
  logPath: string
  /** Resolves when the M2 process exits. */
  exited: Promise<number | null>
  /** Frames M2 actually delivered over the radio link, in delivery order. */
  deliveredFrames(): DeliveredFrame[]
  /** M2's own run report, once the process has written it. */
  report(): Record<string, unknown>
  log(): string
  /** Terminate M2 if it is still running; a station-down test uses this deliberately. */
  stop(): Promise<void>
  /** True once the process has exited. */
  get stopped(): boolean
}

let stationCount = 0

/**
 * Start the real Python M2 WebSocket bridge replaying the committed calibrated ONNX observations.
 *
 * The caller must navigate the dashboard only after this resolves: M2 holds capture until a
 * WebSocket receiver connects, so a readiness probe on its stdout replaces any sleep, and the
 * first dashboard connection is the one that releases the gate.
 */
export async function startStation(options: StationOptions): Promise<M2Station> {
  if (!existsSync(OBSERVATIONS)) {
    throw new Error(`Committed ONNX observations are missing at ${OBSERVATIONS}`)
  }
  const runDir = path.join(E2E_OUTPUT_ROOT, `${String(++stationCount).padStart(2, '0')}-${options.label}`)
  rmSync(runDir, { recursive: true, force: true })
  mkdirSync(runDir, { recursive: true })
  const logPath = path.join(runDir, 'm2.log')
  const reportPath = path.join(runDir, 'm2-report.json')
  const receivedPath = path.join(runDir, 'm2-received.jsonl')

  const argv = [
    '-m', 'crater_m2',
    '--input', OBSERVATIONS,
    ...(options.journalPath ? ['--incident-journal', options.journalPath] : []),
    '--input-ground-z', '0',
    '--duration', String(options.durationS),
    '--drain', String(options.drainS ?? 60),
    '--fps', String(options.fps),
    '--bandwidth', '4096',
    '--latency', '.005',
    '--jitter', '0',
    '--loss', String(options.loss),
    ...(options.blackout === null ? ['--no-blackout'] : ['--blackout', options.blackout]),
    '--queue', String(options.queue ?? 128),
    '--attempts', String(options.attempts ?? 20),
    '--seed', String(options.seed ?? 7),
    '--port', String(WS_PORT),
    '--wait-for-client', String(options.waitForClientS ?? 120),
    '--report', reportPath,
    '--received-jsonl', receivedPath,
  ]

  const child: ChildProcess = spawn(pythonExecutable(), argv, {
    cwd: REPO_ROOT,
    env: {
      ...process.env,
      // No model download, telemetry or cloud call may be reachable from this suite.
      HF_HUB_OFFLINE: '1',
      TRANSFORMERS_OFFLINE: '1',
      HF_HUB_DISABLE_TELEMETRY: '1',
      PYTHONUNBUFFERED: '1',
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  })

  const logFd = openSync(logPath, 'w')
  let transcript = ''
  let stopped = false
  let exitCode: number | null = null
  const append = (chunk: Buffer) => {
    transcript += chunk.toString('utf8')
    try {
      // Best effort: a closed descriptor must not break the test that is reading the log.
      writeSync(logFd, chunk)
    } catch {
      /* ignore */
    }
  }
  child.stdout?.on('data', append)
  child.stderr?.on('data', append)

  const exited = new Promise<number | null>((resolve) => {
    child.once('exit', (code) => {
      stopped = true
      exitCode = code
      try {
        closeSync(logFd)
      } catch {
        /* ignore */
      }
      resolve(code)
    })
  })

  await new Promise<void>((resolve, reject) => {
    const deadline = setTimeout(() => {
      finish(new Error(`M2 (${options.label}) did not print "${READY_LINE}" within ${READY_TIMEOUT_MS} ms.\n${transcript}`))
    }, READY_TIMEOUT_MS)
    const poll = setInterval(() => {
      if (transcript.includes(READY_LINE)) finish()
      else if (stopped) finish(new Error(`M2 (${options.label}) exited with code ${exitCode} before becoming ready.\n${transcript}`))
    }, 50)
    function finish(error?: Error) {
      clearTimeout(deadline)
      clearInterval(poll)
      if (error) {
        child.kill()
        reject(error)
      } else resolve()
    }
  })

  const readJsonl = (file: string): DeliveredFrame[] =>
    existsSync(file)
      ? readFileSync(file, 'utf8').split('\n').filter((line) => line.trim() !== '').map((line) => JSON.parse(line) as DeliveredFrame)
      : []

  return {
    wsUrl: WS_URL,
    logPath,
    exited,
    deliveredFrames: () => readJsonl(receivedPath),
    report: () => (existsSync(reportPath) ? JSON.parse(readFileSync(reportPath, 'utf8')) : {}),
    log: () => transcript,
    get stopped() {
      return stopped
    },
    async stop() {
      if (stopped) return
      child.kill()
      await Promise.race([exited, new Promise((resolve) => setTimeout(resolve, 10_000))])
      if (!stopped) child.kill('SIGKILL')
      await Promise.race([exited, new Promise((resolve) => setTimeout(resolve, 5_000))])
    },
  }
}
