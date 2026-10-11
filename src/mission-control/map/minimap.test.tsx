// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { MapModel, TrailPoint } from '../model/types'
import { MiniMap } from './MiniMap'
import { MINIMAP_SIZE, miniMapProjection, miniMapTrail } from './minimapGeometry'

afterEach(cleanup)
const point = (x: number, y: number, seq: number, gap = 0): TrailPoint => ({ x, y, seq, gap, t: seq * 1000 })
function model(): MapModel {
  return {
    trail: [point(0, 0, 0), point(2, 4, 1)],
    hazards: [{ key: 'r:h', id: 'h', type: 'rock', x: -3, y: 7, z: 0, unc: 0.4, confidence: 0.8, observedMs: 1000, ageMs: 0, firstRxMs: 1000 }],
    rover: { x: 2, y: 4, unc: 0.2, seq: 1, roverId: 'r', cog: null, latencyMs: 100 },
    selectedKey: null, posture: 'NOMINAL', lastCaptureMs: 1000, maxSpeed: 0,
    layers: { trail: true, unc: true, rings: true, envelope: true, cog: true },
    filters: { rock: true, crater: true, slope: true, unknown: true }, minConfidence: 0,
    agedHazardMs: 30000, recoveryStartMs: null, intervalMs: 1000,
  }
}

describe('mission minimap geometry', () => {
  it('keeps north up and uses an equal metric scale for both axes', () => {
    const { project } = miniMapProjection([{ x: 0, y: 0 }])
    const origin = project({ x: 0, y: 0 }), east = project({ x: 1, y: 0 }), north = project({ x: 0, y: 1 })
    expect(east.x).toBeGreaterThan(origin.x)
    expect(north.y).toBeLessThan(origin.y)
    expect(east.x - origin.x).toBeCloseTo(origin.y - north.y)
    expect(east.y).toBe(origin.y)
  })
  it('fits accepted extents and the origin with margin, including negative coordinates', () => {
    const points = [{ x: -800, y: 120 }, { x: 300, y: -1500 }, { x: 0, y: 0 }]
    const { project } = miniMapProjection(points)
    for (const p of points) {
      const v = project(p)
      expect(v.x).toBeGreaterThan(0); expect(v.x).toBeLessThan(MINIMAP_SIZE)
      expect(v.y).toBeGreaterThan(0); expect(v.y).toBeLessThan(MINIMAP_SIZE)
    }
  })
  it('has a finite nonzero scale for an empty scene or coincident fixes', () => {
    for (const points of [[], [{ x: 0, y: 0 }, { x: 0, y: 0 }]]) {
      const view = miniMapProjection(points)
      expect(view.spanM).toBeGreaterThan(0)
      expect(Number.isFinite(view.scale)).toBe(true)
      expect(view.project({ x: 0, y: 0 })).toEqual({ x: 80, y: 80 })
    }
  })
  it('never renders an inferred sequence gap as a solid observed path', () => {
    const trail = [point(0, 0, 0), point(1, 1, 1), point(4, 4, 4, 2), point(5, 5, 5)]
    const paths = miniMapTrail(trail, p => p)
    expect(paths.observed).toBe('M0,0L1,1M4,4L5,5')
    expect(paths.gaps).toBe('M1,1L4,4')
  })
})

describe('mission minimap evidence and interaction', () => {
  it('shows an empty state and no rover or hazard markers before accepted telemetry', () => {
    const m = { ...model(), rover: null, trail: [], hazards: [] }
    const { container } = render(<MiniMap model={m} viewport={null} compact={false} onFit={vi.fn()} />)
    expect(screen.getByText('NO ACCEPTED FIX')).toBeTruthy()
    expect(container.querySelector('.mc-minimap__rover')).toBeNull()
    expect(container.querySelector('.mc-minimap__selection')).toBeNull()
    expect(screen.getByRole('button', { name: 'FIT MISSION' }).hasAttribute('disabled')).toBe(true)
  })
  it('retains the accepted fix and labels it last known when stale or disconnected', () => {
    const m = model(), fit = vi.fn()
    const { container, rerender } = render(<MiniMap model={m} viewport={null} compact={false} onFit={fit} />)
    const original = container.querySelector('.mc-minimap__rover')?.innerHTML
    expect(original).toContain('E 2 m, N 4 m; uncertainty radius 0.2 m')
    for (const posture of ['STALE', 'BLACKOUT', 'TRANSPORT_DOWN'] as const) {
      rerender(<MiniMap model={{ ...m, posture }} viewport={null} compact={false} onFit={fit} />)
      expect(screen.getByText('LAST KNOWN · 1')).toBeTruthy()
      expect(container.querySelector('.mc-minimap__rover')?.innerHTML).toBe(original)
    }
    fireEvent.click(screen.getByRole('button', { name: 'FIT MISSION' }))
    expect(fit).toHaveBeenCalledOnce()
    expect(m.rover?.x).toBe(2)
  })
  it('respects accepted hazard selection and type filters', () => {
    const m = { ...model(), selectedKey: 'r:h' }
    const { container, rerender } = render(<MiniMap model={m} viewport={null} compact={false} onFit={vi.fn()} />)
    expect(container.querySelector('.mc-minimap__selection title')?.textContent).toBe('Selected hazard: h')
    rerender(<MiniMap model={{ ...m, filters: { ...m.filters, rock: false } }} viewport={null} compact={false} onFit={vi.fn()} />)
    expect(container.querySelector('.mc-minimap__selection')).toBeNull()
    expect(container.textContent).not.toContain('h: E -3 m')
  })
  it('starts collapsed on small screens and supports keyboard-accessible expansion', () => {
    render(<MiniMap model={model()} viewport={null} compact={true} onFit={vi.fn()} />)
    const toggle = screen.getByRole('button', { name: 'Toggle mission minimap' })
    expect(toggle.getAttribute('aria-expanded')).toBe('false')
    expect(screen.queryByRole('img')).toBeNull()
    fireEvent.click(toggle)
    expect(toggle.getAttribute('aria-expanded')).toBe('true')
    expect(screen.getByRole('img', { name: /North-up overview/ })).toBeTruthy()
    fireEvent.click(toggle)
    expect(screen.queryByRole('img')).toBeNull()
  })
})
