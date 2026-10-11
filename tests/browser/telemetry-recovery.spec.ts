import { expect, test } from '@playwright/test'
import { Dashboard, type DashboardSnapshot } from './support/dashboard'
import { collectBrowserDiagnostics, EXPECTED_STATION_LOSS } from './support/diagnostics'
import { startStation, type M2Station } from './support/m2-station'

/**
 * Loss, blackout and recovery against the real M2 radio simulation.
 *
 * Two different interruptions must never be conflated:
 *   - a simulated lunar-radio blackout, where the station WebSocket stays up and frames stop;
 *   - a station WebSocket disconnection, where Mission Control cannot know the radio state.
 */

let station: M2Station | undefined

test.afterEach(async () => {
  await station?.stop()
  station = undefined
})

/** Longest run of consecutive samples whose accepted count never moved. */
function longestFrozenRun(samples: DashboardSnapshot[]): DashboardSnapshot[] {
  let best: DashboardSnapshot[] = []
  let run: DashboardSnapshot[] = []
  for (const sample of samples) {
    if (run.length > 0 && run[0].accepted === sample.accepted) run.push(sample)
    else run = [sample]
    if (run.length > best.length) best = [...run]
  }
  return best
}

test('holds rover state through the simulated radio blackout and advances after recovery', async ({ page }) => {
  const diagnostics = collectBrowserDiagnostics(page, EXPECTED_STATION_LOSS)
  // A long blackout inside the radio simulation. The WebSocket is never interrupted, so any
  // pause the dashboard shows comes from telemetry that genuinely did not arrive.
  //
  // The blackout opens at mission second 9, after the ~6 s cinematic intro has handed off and
  // the first frames have been accepted, and lasts 12 s, so the interruption still falls well
  // inside the sampling window below on a slow hosted runner. M2 delivers 30/30 regardless,
  // through retransmission once the link returns.
  station = await startStation({
    label: 'radio-blackout',
    durationS: 16,
    drainS: 40,
    fps: 2,
    loss: 0.25,
    blackout: '9:21',
  })

  await page.goto('/')
  const dashboard = new Dashboard(page)
  await dashboard.waitForIntro()

  // First frames arrive before the blackout window opens.
  await expect(dashboard.counter('ACCEPTED')).not.toHaveText('0', { timeout: 60_000 })
  expect(await dashboard.transportStatus()).toBe('CONNECTED')

  // Sample the dashboard for the rest of the replay, then reason about what it showed.
  const samples: DashboardSnapshot[] = []
  const started = Date.now()
  while (Date.now() - started < 70_000) {
    const sample = await dashboard.snapshot()
    samples.push(sample)
    if (sample.accepted >= 30) break
    await page.waitForTimeout(250)
  }

  const context = () => `samples=${JSON.stringify(samples.slice(-10))}\nM2 log: ${station?.logPath}`

  // Every accepted frame arrived over a connected WebSocket: the blackout is a radio event,
  // and Mission Control never claimed the station itself was down.
  expect(
    samples.filter((sample) => sample.transport !== 'CONNECTED'),
    context(),
  ).toEqual([])
  expect(
    samples.filter((sample) => sample.posture === 'TRANSPORT DOWN'),
    context(),
  ).toEqual([])
  expect(
    samples.filter((sample) => sample.bannerKicker.includes('STATION TRANSPORT DOWN')),
    context(),
  ).toEqual([])

  // The dashboard must not advance rover state while no telemetry is accepted.
  const frozen = longestFrozenRun(samples)
  const frozenMs = frozen.length > 1 ? frozen[frozen.length - 1].atMs - frozen[0].atMs : 0
  expect(frozenMs, `blackout hold too short; ${context()}`).toBeGreaterThan(6_000)
  expect(new Set(frozen.map((sample) => sample.sequence)).size, context()).toBe(1)
  expect(new Set(frozen.map((sample) => sample.north)).size, context()).toBe(1)
  expect(new Set(frozen.map((sample) => sample.east)).size, context()).toBe(1)
  // Throughout the hold the fix is labelled as aged, not presented as current.
  expect(
    frozen.filter((sample) => sample.ageState !== 'STALE'),
    context(),
  ).toEqual([])
  expect(await dashboard.roverHeadLabel()).toBe('LAST KNOWN POSITION')

  // After recovery the retransmitted frames are accepted and the displayed fix moves on.
  const final = samples[samples.length - 1]
  expect(final.accepted, context()).toBeGreaterThan(frozen[0].accepted)
  expect(final.sequence ?? -1, context()).toBeGreaterThan(frozen[0].sequence ?? -1)
  expect(final.north, context()).not.toBe(frozen[0].north)
  await expect(dashboard.counter('ACCEPTED')).toHaveText('30', { timeout: 60_000 })
  expect(await dashboard.counterValue('INVALID')).toBe(0)
  expect(await dashboard.roverSequence()).toBe(29)

  // The journal recorded the accepted frames it actually applied.
  await expect(dashboard.eventStream).toContainText('FRAME')

  // M2 agrees it ran a lossy link with a blackout and still delivered everything it generated.
  await station.exited
  const report = station.report() as {
    completed?: boolean
    transport?: { generated?: number; delivered?: number }
    link?: { blackouts?: number[][]; lossProbability?: number }
  }
  expect(report.completed).toBe(true)
  expect(report.transport?.generated).toBe(30)
  expect(report.transport?.delivered).toBe(30)
  expect(report.link?.lossProbability).toBeCloseTo(0.25, 5)
  expect(report.link?.blackouts).toEqual([[9, 21]])

  expect(diagnostics.problems()).toEqual([])
})

test('distinguishes a station WebSocket loss from the simulated radio blackout', async ({ page }) => {
  const diagnostics = collectBrowserDiagnostics(page, EXPECTED_STATION_LOSS)
  station = await startStation({ label: 'station-down', durationS: 20, drainS: 20, fps: 4, loss: 0, blackout: null })

  await page.goto('/')
  const dashboard = new Dashboard(page)
  await dashboard.waitForIntro()
  await expect(dashboard.counter('ACCEPTED')).not.toHaveText('0', { timeout: 60_000 })
  expect(await dashboard.transportStatus()).toBe('CONNECTED')

  // While the socket is up, an old recording is reported as stale data over a working transport.
  await expect(dashboard.banner.locator('.mc-banner__kicker')).toHaveText(
    'MISSION CONTROL · TRANSPORT UP, DATA STALE',
  )
  await expect(dashboard.postureLabel).toHaveText('STALE')

  const held = await dashboard.snapshot()
  expect(held.sequence).not.toBeNull()

  // Now take the station away mid-mission. This is not a radio blackout.
  await station.stop()

  await expect(dashboard.postureLabel).toHaveText('TRANSPORT DOWN', { timeout: 30_000 })
  await expect(dashboard.banner.locator('.mc-banner__kicker')).toHaveText(
    'MISSION CONTROL · STATION TRANSPORT DOWN',
  )
  await expect(dashboard.banner.locator('.mc-banner__title')).toHaveText('Station connection lost')
  await expect(dashboard.banner.locator('.mc-banner__l2')).toContainText('radio state is unknown')
  await expect(dashboard.postureSub).toContainText('Station WebSocket disconnected')
  await expect(dashboard.eventStream).toContainText('STATION DOWN')

  // The last accepted telemetry is retained and labelled, never extrapolated.
  const afterLoss = await dashboard.snapshot()
  expect(afterLoss.transport).toBe('DISCONNECTED')
  expect(afterLoss.sequence).toBe(held.sequence)
  expect(afterLoss.east).toBe(held.east)
  expect(afterLoss.north).toBe(held.north)
  expect(afterLoss.accepted).toBe(held.accepted)
  expect(afterLoss.ageState).toBe('LAST KNOWN')
  expect(await dashboard.roverHeadLabel()).toBe('LAST KNOWN POSITION')

  // No telemetry arrives after the station is gone.
  await page.waitForTimeout(3_000)
  const settled = await dashboard.snapshot()
  expect(settled.accepted).toBe(held.accepted)
  expect(settled.sequence).toBe(held.sequence)

  expect(diagnostics.problems()).toEqual([])
})
