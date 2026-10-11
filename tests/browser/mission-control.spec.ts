import { readFileSync } from 'node:fs'
import { expect, test } from '@playwright/test'
import { OBSERVATIONS } from './support/config'
import { Dashboard } from './support/dashboard'
import { collectBrowserDiagnostics, EXPECTED_STATION_LOSS, signedFixed, utcClock } from './support/diagnostics'
import { startStation, type M2Station } from './support/m2-station'

/** The committed calibrated ONNX recording, read straight from the repository. */
const recorded = readFileSync(OBSERVATIONS, 'utf8')
  .split('\n')
  .filter((line) => line.trim() !== '')
  .map(
    (line) =>
      JSON.parse(line) as {
        sequence: number
        capturedAt: string
        roverId: string
        roverPosition: { xM: number; yM: number; zM: number }
        detections: { id: string; type: string }[]
      },
  )

/** Exactly the radio parameters `scripts/start-demo.ps1` gives the judge Quick Demo. */
const DEMO_LINK = { durationS: 10, drainS: 60, fps: 10, loss: 0.25, blackout: '.5:5' } as const
/** A short uninterrupted replay for the interaction and layout checks. */
const QUICK_LINK = { durationS: 4, drainS: 20, fps: 5, loss: 0, blackout: null } as const

let station: M2Station | undefined

test.afterEach(async () => {
  await station?.stop()
  station = undefined
})

test('the recording under test is the committed 30-frame ONNX capture', () => {
  expect(recorded).toHaveLength(30)
  expect(recorded.map((frame) => frame.sequence)).toEqual([...Array(30).keys()])
  expect(new Set(recorded.map((frame) => frame.roverId))).toEqual(new Set(['rover-1']))
})

test('loads in LIVE mode, plays the intro and accepts all 30 recorded ONNX frames', async ({ page }) => {
  const diagnostics = collectBrowserDiagnostics(page, EXPECTED_STATION_LOSS)
  station = await startStation({ label: 'demo-replay', ...DEMO_LINK })

  await page.goto('/')
  const dashboard = new Dashboard(page)

  // --- initial UI -----------------------------------------------------------------------
  await dashboard.waitForIntro()
  await expect(dashboard.sourceChip).toHaveText('LIVE')
  // The DEMO mock control must never appear against real telemetry.
  await expect(dashboard.demoControl).toHaveCount(0)
  await expect(dashboard.configurationError).toHaveCount(0)
  await expect(dashboard.roverPanel).toBeVisible()
  await expect(dashboard.commsPanel).toBeVisible()
  await expect(dashboard.packetPanel).toBeVisible()
  await expect(dashboard.inventory).toBeVisible()
  await expect(dashboard.inspector).toBeVisible()
  await expect(dashboard.eventStream).toBeVisible()
  await expect(dashboard.mapCanvas).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Tactical Map' })).toBeVisible()
  expect(await dashboard.transportStatus()).toBe('CONNECTED')

  // --- the browser's own accepted count, not M2's delivery total ------------------------
  // M2 reporting 30/30 delivered is not evidence that Mission Control accepted 30.
  await expect(dashboard.counter('ACCEPTED')).toHaveText('30', { timeout: 120_000 })

  const counters = await dashboard.packetCounters()
  expect(counters['ACCEPTED']).toBe(30)
  expect(counters['RECEIVED']).toBeGreaterThanOrEqual(30)
  expect(counters['INVALID']).toBe(0)
  expect(counters['DUPLICATE']).toBe(0)
  expect(counters['OUT-OF-ORDER']).toBe(0)
  // Mission Control infers gaps from accepted sequence numbers. Zero gaps plus 30 accepted
  // frames ending at sequence 29 means exactly sequences 0-29 were accepted, with none missing.
  expect(counters['SEQ GAPS*']).toBe(0)
  expect(await dashboard.roverSequence()).toBe(29)
  expect(await dashboard.roverId()).toBe('rover-1')

  // --- honest age while the station is still connected ---------------------------------
  // The recording is historical, so Mission Control must show it as old, not as nominal.
  expect(await dashboard.transportStatus()).toBe('CONNECTED')
  await expect(dashboard.postureLabel).toHaveText('STALE')
  const age = await dashboard.informationAge()
  expect(age.state).toBe('STALE')
  expect(age.seconds ?? 0).toBeGreaterThan(600)
  expect(await dashboard.roverHeadLabel()).toBe('LAST KNOWN POSITION')
  await expect(dashboard.banner.locator('.mc-banner__kicker')).toHaveText(
    'MISSION CONTROL · TRANSPORT UP, DATA STALE',
  )

  // --- displayed rover fix equals actual M2 output -------------------------------------
  // `--received-jsonl` is flushed per delivery, so it is readable before M2 exits.
  const delivered = station.deliveredFrames()
  expect(delivered.map((frame) => frame.sequence)).toEqual([...Array(30).keys()])
  const last = delivered[delivered.length - 1]
  expect(await dashboard.roverEnu()).toEqual({
    EAST: signedFixed(last.roverPosition.xM),
    NORTH: signedFixed(last.roverPosition.yM),
    UP: signedFixed(last.roverPosition.zM),
  })
  const facts = await dashboard.roverFacts()
  expect(facts['Position ±']).toBe(`± ${last.positionUncertaintyRadiusM.toFixed(2)} m`)

  // --- historical capture timestamps are preserved end to end --------------------------
  const recordedLast = recorded[recorded.length - 1]
  expect(last.capturedAt).toBe(recordedLast.capturedAt)
  expect(facts['Capture · rover']).toBe(utcClock(recordedLast.capturedAt))

  // --- at least one hazard position equals actual M2 output ----------------------------
  const hazard = last.hazards[0]
  expect(hazard).toBeDefined()
  await dashboard.inventoryRow(hazard.id).click()
  const inspected = await dashboard.inspectorFacts()
  expect(inspected['E · N · U']).toBe(
    [hazard.position.xM, hazard.position.yM, hazard.position.zM].map((value) => signedFixed(value)).join('  '),
  )
  expect(inspected['Uncertainty']).toBe(`± ${hazard.uncertaintyRadiusM.toFixed(2)} m radius`)
  expect(inspected['Observed · rover clk']).toBe(`${utcClock(hazard.observedAt)}Z`)

  // Every hazard M2 delivered is tracked, and nothing else is.
  expect(new Set(await dashboard.inventoryIds())).toEqual(new Set(last.hazards.map((h) => h.id)))
  expect(await dashboard.mapHasDrawnContent()).toBe(true)

  // --- M2's own account of the same run ------------------------------------------------
  await station.exited
  const report = station.report() as {
    completed?: boolean
    transport?: { generated?: number; delivered?: number }
  }
  expect(report.completed).toBe(true)
  expect(report.transport?.generated).toBe(30)
  expect(report.transport?.delivered).toBe(30)

  expect(diagnostics.problems()).toEqual([])
})

test('hazard selection and inspection place actual M2 observations on the map', async ({ page }) => {
  const diagnostics = collectBrowserDiagnostics(page, EXPECTED_STATION_LOSS)
  station = await startStation({ label: 'hazard-inspection', ...QUICK_LINK })

  await page.goto('/')
  const dashboard = new Dashboard(page)
  await dashboard.waitForIntro()
  await expect(dashboard.counter('ACCEPTED')).not.toHaveText('0', { timeout: 60_000 })
  await expect(dashboard.inventoryRows().first()).toBeVisible()

  // Nothing is selected until the operator selects it.
  await expect(dashboard.inspector).toContainText('No hazard selected')

  const rows = await dashboard.inventoryIds()
  expect(rows.length).toBeGreaterThan(0)
  const target = rows[0]

  await dashboard.inventoryRow(target).click()
  await expect(dashboard.inspector).toContainText(target)
  await expect(dashboard.inventoryRow(target)).toHaveAttribute('aria-pressed', 'true')
  const inspected = await dashboard.inspectorFacts()
  expect(inspected['From rover fix']).toMatch(/^\d+\.\d{2} m · \d{3}°$/)
  expect(Number(inspected['Observations'])).toBeGreaterThan(0)

  // Centre the map on the selected hazard, then read the map's own inverse projection back.
  await station.exited
  const delivered = station.deliveredFrames()
  const observed = delivered[delivered.length - 1].hazards.find((hazard) => hazard.id === target)
  expect(observed).toBeDefined()

  await dashboard.inspector.getByRole('button', { name: 'CENTER ON MAP' }).click()
  await expect(page.locator('.mc-follow')).toHaveAttribute('aria-pressed', 'false')
  await expect
    .poll(async () => (await dashboard.cursorWorld())?.north ?? null, { timeout: 30_000, intervals: [400] })
    .toBeCloseTo(observed!.position.yM, 0)
  const centred = await dashboard.cursorWorld()
  expect(centred!.east).toBeCloseTo(observed!.position.xM, 0)

  // ESC clears the selection, as the inspector advertises.
  await page.keyboard.press('Escape')
  await expect(dashboard.inspector).toContainText('No hazard selected')

  expect(diagnostics.problems()).toEqual([])
})

test('renders without horizontal overflow on desktop and mobile viewports', async ({ page }) => {
  const diagnostics = collectBrowserDiagnostics(page, EXPECTED_STATION_LOSS)
  station = await startStation({ label: 'responsive', ...QUICK_LINK })

  await page.goto('/')
  const dashboard = new Dashboard(page)
  await dashboard.waitForIntro()
  await expect(dashboard.counter('ACCEPTED')).not.toHaveText('0', { timeout: 60_000 })

  for (const viewport of [
    { name: 'desktop', width: 1600, height: 1000 },
    { name: 'laptop', width: 1280, height: 800 },
    { name: 'mobile', width: 390, height: 844 },
  ]) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height })
    // Let the grid, the ResizeObserver and the map canvas settle.
    await page.waitForTimeout(700)
    await expect(dashboard.roverPanel, viewport.name).toBeVisible()
    await expect(dashboard.packetPanel, viewport.name).toBeVisible()
    await expect(dashboard.inventory, viewport.name).toBeVisible()
    await expect(dashboard.mapCanvas, viewport.name).toBeVisible()
    const box = await dashboard.mapCanvas.boundingBox()
    expect(box!.width, `${viewport.name} map width`).toBeGreaterThan(200)
    expect(box!.height, `${viewport.name} map height`).toBeGreaterThan(200)
    expect(await dashboard.horizontalOverflowPx(), `${viewport.name} horizontal overflow`).toBeLessThanOrEqual(1)
  }

  expect(diagnostics.problems()).toEqual([])
})
