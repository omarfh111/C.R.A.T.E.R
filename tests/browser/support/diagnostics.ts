import type { Page } from '@playwright/test'

export type BrowserDiagnostics = {
  /** Uncaught exceptions and console errors the page produced, minus the allowed patterns. */
  problems(): string[]
  /** Everything recorded, including allowed entries. Useful in failure messages. */
  all(): string[]
}

/**
 * Collect uncaught page errors and console errors. Must be installed before the first navigation.
 *
 * `allow` exists for the station-down test: Chromium reports a closed WebSocket as a console
 * error from the network stack, which is the expected observation there rather than a defect.
 */
export function collectBrowserDiagnostics(page: Page, allow: RegExp[] = []): BrowserDiagnostics {
  const entries: string[] = []
  const allowed = (text: string) => allow.some((pattern) => pattern.test(text))

  page.on('pageerror', (error) => {
    entries.push(`pageerror: ${error.message}`)
  })
  page.on('console', (message) => {
    if (message.type() === 'error') entries.push(`console.error: ${message.text()}`)
  })
  page.on('requestfailed', (request) => {
    // A failed WebSocket upgrade is reported here too; a failed asset request is a real defect.
    entries.push(`requestfailed: ${request.url()} (${request.failure()?.errorText ?? 'unknown'})`)
  })

  return {
    problems: () => entries.filter((entry) => !allowed(entry)),
    all: () => [...entries],
  }
}

/**
 * Chromium reports a WebSocket whose server has gone away as a console error and a failed
 * request. Both are the expected observation once an M2 replay finishes or is stopped on
 * purpose, so they are allowed only in the tests that expect the station to be gone.
 */
export const EXPECTED_STATION_LOSS: RegExp[] = [
  /WebSocket connection to .* failed/i,
  /ws:\/\/127\.0\.0\.1:\d+\/telemetry/,
]

/** Signed fixed-point exactly as Mission Control renders it: +1.20 / U+2212 0.40 / 0.00. */
export function signedFixed(value: number, decimals = 2): string {
  const sign = value < 0 ? '−' : value > 0 ? '+' : ''
  return sign + Math.abs(value).toFixed(decimals)
}

/** HH:MM:SS.mmm in UTC, as the rover and hazard clocks are rendered. */
export function utcClock(isoTimestamp: string): string {
  return new Date(Date.parse(isoTimestamp)).toISOString().slice(11, 23)
}
