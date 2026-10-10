import { describe, expect, it } from 'vitest'
import { canUseWebGL } from './lunarScene'

describe('WebGL capability', () => {
  it('accepts a usable WebGL 2 context', () => {
    const canvas = { getContext: () => ({ getContextAttributes: () => ({ alpha: false }) }) }
    expect(canUseWebGL(canvas as unknown as HTMLCanvasElement)).toBe(true)
  })
  it('falls back for missing or lost contexts', () => {
    expect(canUseWebGL({ getContext: () => null } as unknown as HTMLCanvasElement)).toBe(false)
    expect(canUseWebGL({ getContext: () => ({ getContextAttributes: () => null }) } as unknown as HTMLCanvasElement)).toBe(false)
  })
})
