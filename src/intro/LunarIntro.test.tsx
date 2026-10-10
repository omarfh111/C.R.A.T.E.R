// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mountScene = vi.hoisted(() => vi.fn())
vi.mock('./lunarScene', () => ({ INTRO_DURATION_MS: 5200, mountLunarScene: mountScene }))

import { LunarIntro } from './LunarIntro'

function reducedMotion(matches: boolean) {
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    value: () => ({ matches, addListener: vi.fn(), removeListener: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn() }),
  })
}

beforeEach(() => {
  vi.useFakeTimers()
  mountScene.mockReset()
  mountScene.mockReturnValue(vi.fn())
  reducedMotion(false)
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('lunar intro flow', () => {
  it('plays on launch and completes after the timed dissolve', () => {
    const complete = vi.fn()
    const { container } = render(<LunarIntro onComplete={complete} />)
    expect(screen.getByRole('button', { name: /skip intro/i })).toBeTruthy()
    expect(mountScene).toHaveBeenCalledTimes(1)
    act(() => vi.advanceTimersByTime(5199))
    expect(complete).not.toHaveBeenCalled()
    expect(container.querySelector('.lunar-intro')).toBeTruthy()
    act(() => vi.advanceTimersByTime(621))
    expect(complete).toHaveBeenCalledTimes(1)
  })

  it('skips immediately without waiting for the full sequence', () => {
    const complete = vi.fn()
    const { container } = render(<LunarIntro onComplete={complete} />)
    fireEvent.click(screen.getByRole('button', { name: /skip intro/i }))
    expect(container.querySelector('.lunar-intro--exiting')).toBeTruthy()
    act(() => vi.advanceTimersByTime(620))
    expect(complete).toHaveBeenCalledTimes(1)
  })

  it('uses the still image and shorter timeline if WebGL fails', () => {
    mountScene.mockImplementation(() => { throw new Error('WebGL unavailable') })
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    const complete = vi.fn()
    const { container } = render(<LunarIntro onComplete={complete} />)
    expect(container.querySelector('.lunar-intro--fallback')).toBeTruthy()
    expect(container.querySelector('canvas')).toBeNull()
    act(() => vi.advanceTimersByTime(4220))
    expect(complete).toHaveBeenCalledTimes(1)
  })

  it('honors reduced motion without mounting WebGL', () => {
    reducedMotion(true)
    const complete = vi.fn()
    const { container } = render(<LunarIntro onComplete={complete} />)
    expect(mountScene).not.toHaveBeenCalled()
    expect(container.querySelector('canvas')).toBeNull()
    act(() => vi.advanceTimersByTime(700))
    act(() => vi.advanceTimersByTime(1))
    expect(complete).toHaveBeenCalledTimes(1)
  })

  it('releases scene resources and restores page scrolling on unmount', () => {
    const dispose = vi.fn()
    mountScene.mockReturnValue(dispose)
    const previous = document.body.style.overflow
    const { unmount } = render(<LunarIntro onComplete={vi.fn()} />)
    expect(document.body.style.overflow).toBe('hidden')
    unmount()
    expect(dispose).toHaveBeenCalledTimes(1)
    expect(document.body.style.overflow).toBe(previous)
  })
})
