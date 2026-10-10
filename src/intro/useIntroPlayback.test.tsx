// @vitest-environment jsdom
import { act, cleanup, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useIntroPlayback } from './useIntroPlayback'

beforeEach(() => window.sessionStorage.clear())
afterEach(() => { cleanup(); vi.restoreAllMocks() })

describe('tab-scoped intro playback', () => {
  it('plays on first visit and bypasses a reload even during playback', () => {
    const first = renderHook(() => useIntroPlayback())
    expect(first.result.current.introVisible).toBe(true)
    expect(window.sessionStorage.getItem('crater:intro-started:v1')).toBe('1')
    first.unmount()

    const refresh = renderHook(() => useIntroPlayback())
    expect(refresh.result.current.introVisible).toBe(false)
  })

  it('plays again in a fresh tab session', () => {
    renderHook(() => useIntroPlayback()).unmount()
    window.sessionStorage.clear() // A separate tab has an independent session store.
    expect(renderHook(() => useIntroPlayback()).result.current.introVisible).toBe(true)
  })

  it('replays without clearing the tab marker', () => {
    const first = renderHook(() => useIntroPlayback())
    act(() => first.result.current.startHandoff())
    expect(first.result.current.handoffStarted).toBe(true)
    act(() => first.result.current.completeIntro())
    expect(first.result.current.introVisible).toBe(false)
    expect(first.result.current.handoffStarted).toBe(false)
    act(() => first.result.current.replayIntro())
    expect(first.result.current.introVisible).toBe(true)
    expect(first.result.current.handoffStarted).toBe(false)
    expect(first.result.current.introRun).toBe(1)
    expect(window.sessionStorage.getItem('crater:intro-started:v1')).toBe('1')
    first.unmount()
    expect(renderHook(() => useIntroPlayback()).result.current.introVisible).toBe(false)
  })

  it('keeps running if session storage is unavailable', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked') })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked') })
    expect(() => renderHook(() => useIntroPlayback())).not.toThrow()
  })
})
