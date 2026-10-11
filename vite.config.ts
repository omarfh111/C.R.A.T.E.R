// `defineConfig` comes from vitest/config, which re-exports Vite's own and adds the `test`
// key's types. The build configuration below is unchanged.
import { defaultExclude, defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  test: {
    // tests/browser belongs to Playwright: those specs drive a real Chromium against a live M2
    // station, and Vitest's default `**/*.spec.ts` pattern would otherwise collect them.
    exclude: [...defaultExclude, 'tests/browser/**'],
  },
})
