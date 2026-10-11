import { defineConfig, devices } from '@playwright/test'
import { BASE_URL, WEB_PORT, WS_URL } from './tests/browser/support/config'

const CI = !!process.env.CI

/**
 * Browser verification for M3 Mission Control against the real M2 WebSocket bridge.
 *
 * The suite serves the production bundle through `vite preview` rather than the dev server:
 * `npm run dev` runs React in development, where StrictMode mounts the telemetry adapter twice
 * and briefly closes the first WebSocket. M2 releases its wait-for-client gate on that first
 * connection, so the dev server adds an avoidable race to the very first frames. Previewing the
 * production build keeps one adapter, one socket and one deterministic frame sequence, and it
 * verifies the bundle that `npm run build` actually ships.
 *
 * `scripts/start-demo.ps1` (the judge-facing Quick Demo) is untouched and still uses the dev
 * server; its deliveries begin after the simulated blackout, well past the StrictMode remount.
 *
 * LIVE mode and the WebSocket URL are baked at build time through Vite's VITE_* process
 * environment, so `.env.local` is never written and an interactive demo session is never
 * disturbed. Tests run one at a time because they each own the loopback WebSocket port.
 */
export default defineConfig({
  testDir: './tests/browser',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: CI,
  // Bounded by design: a replay is at most ~30 s of simulated mission time, and the whole
  // suite must stay well inside the hard ceiling below.
  timeout: 150_000,
  globalTimeout: 8 * 60_000,
  expect: { timeout: 20_000 },
  outputDir: 'test-results/playwright',
  reporter: CI
    ? [
        ['list'],
        ['html', { outputFolder: 'playwright-report', open: 'never' }],
        ['junit', { outputFile: 'test-results/browser-e2e-junit.xml' }],
      ]
    : [['list']],
  use: {
    baseURL: BASE_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
    actionTimeout: 20_000,
    navigationTimeout: 30_000,
  },
  projects: [
    {
      name: 'chromium',
      // Wide enough for the three-rail desktop layout; the responsive test resizes from here.
      use: { ...devices['Desktop Chrome'], viewport: { width: 1600, height: 1000 } },
    },
  ],
  webServer: {
    command: `npm run build && npx vite preview --host 127.0.0.1 --port ${WEB_PORT} --strictPort`,
    url: BASE_URL,
    reuseExistingServer: false,
    timeout: 300_000,
    stdout: 'pipe',
    stderr: 'pipe',
    env: {
      VITE_TELEMETRY_MODE: 'LIVE',
      VITE_TELEMETRY_WS_URL: WS_URL,
    },
  },
})
