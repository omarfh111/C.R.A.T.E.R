import { configDefaults, defineConfig, mergeConfig } from 'vitest/config'
import viteConfig from './vite.config'

// The standalone adapter contract uses Node's test runner, invoked separately in CI, and
// tests/browser belongs to Playwright: those specs drive a real Chromium against a live M2
// station, so Vitest's default `**/*.spec.ts` pattern must not collect them.
export default mergeConfig(viteConfig, defineConfig({
  test: { exclude: [...configDefaults.exclude, 'integrations/**', 'tests/browser/**'] },
}))
