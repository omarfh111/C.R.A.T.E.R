// @vitest-environment jsdom
import { act, cleanup, render, screen } from '@testing-library/react'
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
    const handoff = vi.fn()
    const { container } = render(<LunarIntro onHandoffStart={handoff} onComplete={complete} />)
    expect(screen.queryByRole('button', { name: /skip intro/i })).toBeNull()
    expect(mountScene).toHaveBeenCalledTimes(1)
    act(() => vi.advanceTimersByTime(5199))
    expect(handoff).not.toHaveBeenCalled()
    expect(complete).not.toHaveBeenCalled()
    expect(container.querySelector('.lunar-intro')).toBeTruthy()
    act(() => vi.advanceTimersByTime(1))
    expect(handoff).toHaveBeenCalledTimes(1)
    expect(container.querySelector('.lunar-intro--exiting')).toBeTruthy()
    act(() => vi.advanceTimersByTime(899))
    expect(complete).not.toHaveBeenCalled()
    expect(container.querySelector('.lunar-intro--exiting')).toBeTruthy()
    act(() => vi.advanceTimersByTime(1))
    expect(complete).toHaveBeenCalledTimes(1)
  })

  it('uses the still image and shorter timeline if WebGL fails', () => {
    mountScene.mockImplementation(() => { throw new Error('WebGL unavailable') })
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    const complete = vi.fn()
    const { container } = render(<LunarIntro onHandoffStart={vi.fn()} onComplete={complete} />)
    expect(container.querySelector('.lunar-intro--fallback')).toBeTruthy()
    expect(container.querySelector('canvas')).toBeNull()
    act(() => vi.advanceTimersByTime(4500))
    expect(complete).toHaveBeenCalledTimes(1)
  })

  it('honors reduced motion without mounting WebGL', () => {
    reducedMotion(true)
    const complete = vi.fn()
    const { container } = render(<LunarIntro onHandoffStart={vi.fn()} onComplete={complete} />)
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
    const { unmount } = render(<LunarIntro onHandoffStart={vi.fn()} onComplete={vi.fn()} />)
    expect(document.body.style.overflow).toBe('hidden')
    unmount()
    expect(dispose).toHaveBeenCalledTimes(1)
    expect(document.body.style.overflow).toBe(previous)
  })

  it('uses the same handoff on replay and does not add intro controls', () => {
    const handoff = vi.fn()
    const { container } = render(<LunarIntro replay onHandoffStart={handoff} onComplete={vi.fn()} />)
    expect(container.querySelector('.lunar-intro--replay')).toBeTruthy()
    expect(container.querySelector('button')).toBeNull()
    act(() => vi.advanceTimersByTime(5200))
    expect(handoff).toHaveBeenCalledTimes(1)
    expect(container.querySelector('.lunar-intro--exiting')).toBeTruthy()
  })
})
