import { spawn, type ChildProcess } from 'node:child_process'
import { mkdirSync, mkdtempSync } from 'node:fs'
import path from 'node:path'
import { expect, test } from '@playwright/test'
import { BASE_URL, E2E_OUTPUT_ROOT, pythonExecutable, REPO_ROOT } from './support/config'
import { Dashboard } from './support/dashboard'
import { startStation, type M2Station } from './support/m2-station'

type SavedIncident = {
  eventId: string
  sessionId: string
  kind: string
  question: string
  decision?: string
  frame?: { schemaVersion: number; sequence: number; capturedAt: string } | null
  provenance: { observation: string; radio: string; certifiedMeasurement: boolean }
  job: { state: string; attempt: number; result: unknown }
  reviews: { verdict: string; note: string }[]
}

/** Real model-free HTTP collector with a single persistent database and OS worker lease. */
async function collector(database: string, port = 0): Promise<{ child: ChildProcess; url: string; stop(): Promise<void> }> {
  const child = spawn(pythonExecutable(), [
    '-m', 'crater_assistant.journal', '--database', database, '--port', String(port),
    '--allow-origin', BASE_URL,
    // Deliberately absent sidecar: this suite must not require Ollama or a downloaded model.
    '--assistant-url', 'http://127.0.0.1:1',
  ], { cwd: REPO_ROOT, stdio: ['ignore', 'pipe', 'pipe'] })
  let output = ''
  child.stdout?.on('data', (chunk: Buffer) => { output += chunk.toString() })
  child.stderr?.on('data', (chunk: Buffer) => { output += chunk.toString() })
  try {
    await expect.poll(() => {
      if (child.exitCode !== null) throw new Error(`Collector exited ${child.exitCode}: ${output}`)
      return /Incident collector: (http:\/\/127\.0\.0\.1:\d+)/.test(output)
    }, { timeout: 20_000 }).toBe(true)
  } catch (error) { child.kill(); throw error }
  const url = output.match(/Incident collector: (http:\/\/127\.0\.0\.1:\d+)/)![1]
  return { child, url, async stop() {
    if (child.exitCode !== null) return
    const exit = new Promise<void>((resolve) => child.once('exit', () => resolve()))
    child.kill()
    let timer: ReturnType<typeof setTimeout> | undefined
    try { await Promise.race([exit, new Promise<void>((_, reject) => { timer = setTimeout(() => reject(new Error('Collector did not stop')), 10_000) })]) }
    finally { clearTimeout(timer) }
  } }
}

test('automatic dialogue persists through capture end and collector restart without a model', async ({ page, request }) => {
  mkdirSync(E2E_OUTPUT_ROOT, { recursive: true })
  const directory = mkdtempSync(path.join(E2E_OUTPUT_ROOT, 'incident-dialogue-'))
  const database = path.join(directory, 'incidents.sqlite3')
  let service = await collector(database)
  let station: M2Station | undefined
  const incidents = async (): Promise<SavedIncident[]> => {
    const response = await request.get(service.url + '/incidents')
    expect(response.status()).toBe(200)
    return (await response.json()).incidents as SavedIncident[]
  }
  try {
    station = await startStation({ label: 'dialogue-replay', journalPath: database,
      durationS: 14, drainS: 40, fps: 3, loss: 0.25, blackout: '.5:5' })
    await page.goto('/')
    const dashboard = new Dashboard(page)
    await dashboard.waitForIntro()
    await page.getByText('ROBOT INCIDENT DIALOGUE', { exact: true }).click()
    await page.getByLabel('Incident collector URL').fill(service.url)
    await page.getByRole('button', { name: 'CONNECT JOURNAL', exact: true }).click()
    const sessions = await (await request.get(service.url + '/sessions')).json()
    expect(sessions.sessions).toHaveLength(1)
    const session = sessions.sessions[0] as { sessionId: string; phase: string }
    expect(session.phase).toBe('capturing')
    await page.getByLabel('Producer session').selectOption(session.sessionId)
    await expect.poll(async () => (await incidents()).some(i => i.kind === 'telemetry_stale')).toBe(true)
    const captured = await incidents()
    expect(captured.every(i => i.job.state === 'waiting_capture' && i.job.attempt === 0)).toBe(true)
    expect(captured.some(i => i.frame?.schemaVersion === 1)).toBe(true)
    await expect(dashboard.counter('ACCEPTED')).toHaveText('30', { timeout: 60_000 })
    expect(await station.exited).toBe(0)
    await expect.poll(async () => (await incidents()).every(i => i.job.state === 'waiting_service'), { timeout: 20_000 }).toBe(true)
    await expect(page.getByText(/telemetry stale · WAITING FOR LOCAL AI/).first()).toBeVisible()
    const stale = page.locator('details.mi__source').filter({ has: page.locator('summary', { hasText: 'telemetry stale ·' }) }).first()
    await stale.locator('summary').first().click()
    await expect(stale.getByText('AUTOMATIC QUESTION', { exact: true })).toBeVisible()
    await stale.getByRole('button', { name: 'REVIEW SEPARATELY' }).click()
    await stale.getByLabel('Operator review note').fill('E2E: unavailable model; no generated measurement accepted.')
    await stale.getByRole('button', { name: 'INCONCLUSIVE', exact: true }).click()
    await expect.poll(async () => (await incidents()).some(i => i.reviews.length === 1)).toBe(true)
    await page.getByRole('button', { name: 'DISCONNECT JOURNAL', exact: true }).click()
    const before = await incidents()
    expect(before.length).toBeGreaterThan(0)
    expect(before.every(i => i.job.attempt === 0 && i.job.result === null && i.decision === undefined)).toBe(true)
    expect(before.every(i => i.provenance.observation === 'historical_replay' && i.provenance.radio === 'simulated' && !i.provenance.certifiedMeasurement)).toBe(true)
    const oldPort = Number(new URL(service.url).port)
    await service.stop()
    service = await collector(database, oldPort)
    // A service-availability poll may advance updatedAt; durable evidence/reviews/job outcomes must be identical.
    const durable = (rows: SavedIncident[]) => rows.map(i => ({ ...i, job: { ...i.job, updatedAt: null } }))
    expect(durable(await incidents())).toEqual(durable(before))
    await page.getByRole('button', { name: 'CONNECT JOURNAL', exact: true }).click()
    await expect(page.getByLabel('Producer session')).toBeVisible()
    await expect(page.getByText(/telemetry stale · WAITING FOR LOCAL AI/).first()).toBeVisible()
    await expect(page.getByText(/telemetry stale · WAITING FOR LOCAL AI/)).toHaveCount(before.filter(i => i.kind === 'telemetry_stale').length)
    const frames = station.deliveredFrames()
    expect(frames).toHaveLength(30)
    expect(frames.every(frame => frame.schemaVersion === 1)).toBe(true)
    expect(await dashboard.counterValue('INVALID')).toBe(0)
    expect(await dashboard.counterValue('ACCEPTED')).toBe(30)
    await page.screenshot({ path: path.join(directory, 'incident-dialogue.png'), fullPage: true })
  } finally {
    await station?.stop()
    await service.stop()
  }
})
