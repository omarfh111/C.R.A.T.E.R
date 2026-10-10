import type { CSSProperties } from 'react'
import { HAZARD_STYLE } from '../model/constants'
import type { HazardType } from '../model/types'

/** Typed helper for passing CSS custom properties through `style`. */
export const cssVars = (vars: Record<string, string | number>) => vars as CSSProperties

export const hazardVars = (type: HazardType) => cssVars({ '--h-color': HAZARD_STYLE[type].color, '--h-rgb': HAZARD_STYLE[type].rgb })

/** DOM version of the map glyph: crater ring, rock diamond, slope triangle, unknown square. */
export function HazardGlyph({ type, large = false }: { type: HazardType; large?: boolean }) {
  return <span aria-hidden="true" className={`mc-glyph mc-glyph--${type}${large ? ' mc-glyph--lg' : ''}`} />
}
