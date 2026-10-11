import { configDefaults, defineConfig, mergeConfig } from 'vitest/config'
import viteConfig from './vite.config'

// The standalone adapter contract uses Node's test runner, invoked separately in CI.
export default mergeConfig(viteConfig, defineConfig({
  test: { exclude: [...configDefaults.exclude, 'integrations/**'] },
}))
