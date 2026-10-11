import { expect, type Locator, type Page } from '@playwright/test'

/** One atomic reading of the operational displays. See `Dashboard.snapshot()`. */
export type DashboardSnapshot = {
  atMs: number
  transport: string
  accepted: number
  invalid: number
  sequenceGaps: number
  sequence: number | null
  east: string
  north: string
  posture: string
  bannerKicker: string
  ageState: string
}

/**
 * Read-only accessors for the shipped Mission Control DOM. Deliberately no application source
 * changes: every selector below is an existing `aria-label`, role or class name.
 */
export class Dashboard {
  constructor(readonly page: Page) {}

  // ---- cinematic intro -------------------------------------------------------------------

  get intro(): Locator {
    return this.page.locator('.lunar-intro')
  }

  /** The intro must actually play and then hand off; it is never skipped in a fresh context. */
  async waitForIntro(): Promise<void> {
    await expect(this.intro).toHaveCount(1)
    await expect(this.intro).toHaveCount(0, { timeout: 30_000 })
  }

  // ---- header ----------------------------------------------------------------------------

  get sourceChip(): Locator {
    return this.page.locator('.mc-chip--source strong')
  }

  get demoControl(): Locator {
    return this.page.locator('.mc-demo__toggle')
  }

  get postureLabel(): Locator {
    return this.page.locator('.mc-posture__label')
  }

  get postureSub(): Locator {
    return this.page.locator('.mc-posture__sub')
  }

  // ---- panels ----------------------------------------------------------------------------

  get roverPanel(): Locator {
    return this.page.locator('section[aria-label="Rover"]')
  }

  get commsPanel(): Locator {
    return this.page.locator('section[aria-label="Communications"]')
  }

  get packetPanel(): Locator {
    return this.page.locator('section[aria-label="Packet accounting"]')
  }

  get inventory(): Locator {
    return this.page.locator('section[aria-label="Hazard inventory"]')
  }

  get inspector(): Locator {
    return this.page.locator('section[aria-label="Hazard inspector"]')
  }

  get eventStream(): Locator {
    return this.page.locator('section[aria-label="Event stream"]')
  }

  get mapCanvas(): Locator {
    return this.page.locator('canvas.mc-map__canvas')
  }

  get banner(): Locator {
    return this.page.locator('.mc-banner')
  }

  get configurationError(): Locator {
    return this.page.locator('.mc-config-error')
  }

  // ---- packet accounting -----------------------------------------------------------------

  counter(label: string): Locator {
    return this.packetPanel
      .locator('.mc-counter')
      .filter({ has: this.page.locator('.mc-counter__label', { hasText: label }) })
      .locator('.mc-counter__value')
  }

  async counterValue(label: string): Promise<number> {
    return Number((await this.counter(label).innerText()).trim())
  }

  /** Counters as Mission Control itself reports them, never M2's delivery totals. */
  async packetCounters(): Promise<Record<string, number>> {
    return this.packetPanel.evaluate((panel) => {
      const out: Record<string, number> = {}
      for (const cell of panel.querySelectorAll('.mc-counter')) {
        const label = cell.querySelector('.mc-counter__label')?.textContent?.trim() ?? ''
        out[label] = Number(cell.querySelector('.mc-counter__value')?.textContent?.trim())
      }
      return out
    })
  }

  // ---- rover readouts --------------------------------------------------------------------

  /** Latest accepted sequence as displayed, or null while no frame has been accepted. */
  async roverSequence(): Promise<number | null> {
    const text = (await this.roverPanel.locator('.mc-rover__seq').innerText()).trim()
    const value = Number(text.replace(/^SEQ\s*/, ''))
    return Number.isFinite(value) ? value : null
  }

  async roverId(): Promise<string> {
    return (await this.roverPanel.locator('.mc-rover__id').innerText()).trim()
  }

  /** EAST / NORTH / UP readouts exactly as rendered (true minus sign, two decimals). */
  async roverEnu(): Promise<Record<string, string>> {
    return this.roverPanel.evaluate((panel) => {
      const out: Record<string, string> = {}
      for (const cell of panel.querySelectorAll('.mc-enu__cell')) {
        const axis = cell.querySelector('.mc-enu__axis')?.textContent?.trim() ?? ''
        out[axis] = cell.querySelector('.mc-enu__value')?.textContent?.trim() ?? ''
      }
      return out
    })
  }

  /** The rover panel's definition list, keyed by its term text. */
  async roverFacts(): Promise<Record<string, string>> {
    return this.roverPanel.locator('dl.mc-kv').evaluate((list) => {
      const out: Record<string, string> = {}
      const nodes = Array.from(list.children)
      for (let i = 0; i < nodes.length - 1; i++) {
        if (nodes[i].tagName === 'DT' && nodes[i + 1].tagName === 'DD') {
          out[nodes[i].textContent?.trim() ?? ''] = nodes[i + 1].textContent?.trim() ?? ''
        }
      }
      return out
    })
  }

  /** Information-age readout: seconds since the rover captured the latest accepted frame. */
  async informationAge(): Promise<{ seconds: number | null; state: string }> {
    return this.roverPanel.evaluate((panel) => {
      const raw = panel.querySelector('.mc-age__value')?.textContent?.trim() ?? ''
      const seconds = Number(raw)
      return {
        seconds: Number.isFinite(seconds) ? seconds : null,
        state: panel.querySelector('.mc-age__head span:last-child')?.textContent?.trim() ?? '',
      }
    })
  }

  /** The head label flips to LAST KNOWN POSITION whenever the displayed fix is not current. */
  async roverHeadLabel(): Promise<string> {
    return (await this.roverPanel.locator('.mc-rover__head span').first().innerText()).trim()
  }

  // ---- link ------------------------------------------------------------------------------

  /** Mission Control's own WebSocket transport state: CONNECTING, CONNECTED or DISCONNECTED. */
  async transportStatus(): Promise<string> {
    const text = await this.commsPanel
      .locator('.mc-link__cell')
      .filter({ has: this.page.locator('.mc-link__label', { hasText: 'MC TRANSPORT' }) })
      .locator('.mc-link__status')
      .innerText()
    return text.trim()
  }

  /** The rover-reported radio status carried inside the last accepted frame. */
  async roverLinkStatus(): Promise<string> {
    const text = await this.commsPanel
      .locator('.mc-link__cell')
      .filter({ has: this.page.locator('.mc-link__label', { hasText: 'ROVER LINK' }) })
      .locator('.mc-link__status')
      .innerText()
    return text.trim()
  }

  // ---- hazards ---------------------------------------------------------------------------

  inventoryRows(): Locator {
    return this.inventory.locator('.mc-inv-row')
  }

  inventoryRow(hazardId: string): Locator {
    return this.inventoryRows().filter({ has: this.page.locator('.mc-inv-row__id', { hasText: hazardId }) })
  }

  async inventoryIds(): Promise<string[]> {
    return this.inventory.evaluate((section) =>
      Array.from(section.querySelectorAll('.mc-inv-row__id')).map(
        (node) => node.textContent?.trim().split(/\s+/)[0] ?? '',
      ),
    )
  }

  /** Hazard inspector definition list, keyed by its term text. */
  async inspectorFacts(): Promise<Record<string, string>> {
    return this.inspector.locator('dl.mc-kv').evaluate((list) => {
      const out: Record<string, string> = {}
      const nodes = Array.from(list.children)
      for (let i = 0; i < nodes.length - 1; i++) {
        if (nodes[i].tagName === 'DT' && nodes[i + 1].tagName === 'DD') {
          out[nodes[i].textContent?.trim() ?? ''] = nodes[i + 1].textContent?.trim() ?? ''
        }
      }
      return out
    })
  }

  // ---- map -------------------------------------------------------------------------------

  /** The map's own inverse projection, read from the cursor readout after hovering a point. */
  async cursorWorld(offset?: { dx: number; dy: number }): Promise<{ east: number; north: number } | null> {
    const box = await this.mapCanvas.boundingBox()
    if (!box) throw new Error('Tactical map canvas has no layout box')
    await this.page.mouse.move(box.x + box.width / 2 + (offset?.dx ?? 0), box.y + box.height / 2 + (offset?.dy ?? 0))
    // MissionControl repaints the readout on its 500 ms clock tick.
    await this.page.waitForTimeout(700)
    const text = (await this.page.locator('.mc-nav__cursor').innerText()).trim()
    const match = /^E\s+(\S+)\s+N\s+(\S+)\s+m$/.exec(text)
    if (!match) return null
    const numeric = (value: string) => Number(value.replace('−', '-'))
    return { east: numeric(match[1]), north: numeric(match[2]) }
  }

  /** Proves the tactical map actually rendered the scene rather than leaving a blank canvas. */
  async mapHasDrawnContent(): Promise<boolean> {
    return this.mapCanvas.evaluate((canvas) => {
      const element = canvas as HTMLCanvasElement
      const context = element.getContext('2d')
      if (!context || element.width < 2 || element.height < 2) return false
      const { data } = context.getImageData(0, 0, element.width, element.height)
      // The map clears to #03070c; anything brighter is drawn terrain, trail, rover or hazards.
      let bright = 0
      for (let i = 0; i < data.length; i += 4) {
        if (data[i] + data[i + 1] + data[i + 2] > 120) bright++
      }
      return bright > 500
    })
  }

  // ---- atomic sampling -------------------------------------------------------------------

  /**
   * One consistent reading of the operational displays.
   *
   * Taken in a single page evaluation on purpose: four separate round-trips can straddle an
   * accepted frame and mix an old counter with a new position, which would make a "frozen"
   * window look as if it had moved.
   */
  async snapshot(): Promise<DashboardSnapshot> {
    const raw = await this.page.evaluate(() => {
      const text = (selector: string, root: ParentNode = document) =>
        root.querySelector(selector)?.textContent?.trim() ?? ''
      const linkCell = (label: string) =>
        Array.from(document.querySelectorAll('section[aria-label="Communications"] .mc-link__cell')).find(
          (cell) => cell.querySelector('.mc-link__label')?.textContent?.includes(label) ?? false,
        )
      const counters: Record<string, number> = {}
      for (const cell of document.querySelectorAll('section[aria-label="Packet accounting"] .mc-counter')) {
        counters[cell.querySelector('.mc-counter__label')?.textContent?.trim() ?? ''] = Number(
          cell.querySelector('.mc-counter__value')?.textContent?.trim(),
        )
      }
      const enu: Record<string, string> = {}
      for (const cell of document.querySelectorAll('section[aria-label="Rover"] .mc-enu__cell')) {
        enu[cell.querySelector('.mc-enu__axis')?.textContent?.trim() ?? ''] =
          cell.querySelector('.mc-enu__value')?.textContent?.trim() ?? ''
      }
      return {
        transport: text('.mc-link__status', linkCell('MC TRANSPORT') ?? document),
        counters,
        sequenceText: text('section[aria-label="Rover"] .mc-rover__seq'),
        enu,
        posture: text('.mc-posture__label'),
        bannerKicker: text('.mc-banner__kicker'),
        ageState: text('section[aria-label="Rover"] .mc-age__head span:last-child'),
      }
    })
    const sequence = Number(raw.sequenceText.replace(/^SEQ\s*/, ''))
    return {
      atMs: Date.now(),
      transport: raw.transport,
      accepted: raw.counters['ACCEPTED'],
      invalid: raw.counters['INVALID'],
      sequenceGaps: raw.counters['SEQ GAPS*'],
      sequence: Number.isFinite(sequence) ? sequence : null,
      east: raw.enu['EAST'] ?? '',
      north: raw.enu['NORTH'] ?? '',
      posture: raw.posture,
      bannerKicker: raw.bannerKicker,
      ageState: raw.ageState,
    }
  }

  // ---- layout ----------------------------------------------------------------------------

  async horizontalOverflowPx(): Promise<number> {
    return this.page.evaluate(() => {
      const root = document.documentElement
      return Math.max(0, root.scrollWidth - root.clientWidth, document.body.scrollWidth - root.clientWidth)
    })
  }
}
