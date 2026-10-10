import { useEffect, useImperativeHandle, useRef, type Ref } from 'react'
import type { MapModel } from '../model/types'
import { createTacticalMap, type TacticalMapApi, type TacticalMapCallbacks } from './tacticalMap'

export type TacticalMapHandle = Omit<TacticalMapApi, 'destroy'>

type Props = TacticalMapCallbacks & {
  /** Rebuilt every render; the renderer reads the latest value each animation frame. */
  model: MapModel
  ref?: Ref<TacticalMapHandle>
}

/** Canvas host for the tactical map. Creates the renderer once and releases it (rAF, listeners, ResizeObserver) on unmount. */
export function TacticalMap({ model, ref, ...callbacks }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const apiRef = useRef<TacticalMapApi | null>(null)
  const modelRef = useRef(model)
  const cbRef = useRef(callbacks)
  modelRef.current = model
  cbRef.current = callbacks

  useEffect(() => {
    if (!canvasRef.current) return
    const api = createTacticalMap(canvasRef.current, () => modelRef.current, {
      onHover: (k) => cbRef.current.onHover?.(k),
      onSelect: (k) => cbRef.current.onSelect?.(k),
      onCursor: (c) => cbRef.current.onCursor?.(c),
      onFollowChange: (v) => cbRef.current.onFollowChange?.(v),
      onFrame: (i) => cbRef.current.onFrame?.(i),
    })
    apiRef.current = api
    return () => { api.destroy(); apiRef.current = null }
  }, [])

  useImperativeHandle(ref, () => ({
    setFollow: (v) => apiRef.current?.setFollow(v),
    reboot: () => apiRef.current?.reboot(),
    zoomBy: (f) => apiRef.current?.zoomBy(f),
    centerOn: (x, y) => apiRef.current?.centerOn(x, y),
    fit: (p) => apiRef.current?.fit(p),
  }), [])

  return <canvas ref={canvasRef} className="mc-map__canvas" aria-label="Tactical map in LOCAL_ENU_V1 meters" />
}
