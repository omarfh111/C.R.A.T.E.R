import type { BannerView } from '../model/presenters'
import type { MapLayers } from '../model/types'
import { cssVars, HazardGlyph } from './HazardGlyph'

const LAYERS: [keyof MapLayers, string][] = [['trail', 'TRAIL'], ['unc', 'UNCERTAINTY'], ['rings', 'RANGE RINGS'], ['envelope', 'TRAVEL ENVELOPE'], ['cog', 'COURSE']]

export function MapBrackets() {
  return <>
    <span className="mc-map__bracket mc-map__bracket--tl" /><span className="mc-map__bracket mc-map__bracket--tr" />
    <span className="mc-map__bracket mc-map__bracket--bl" /><span className="mc-map__bracket mc-map__bracket--br" />
  </>
}

export function MapTitle({ layers, onToggle }: { layers: MapLayers; onToggle: (k: keyof MapLayers) => void }) {
  return (
    <div className="mc-map__title">
      <div className="mc-map__heading">
        <h2>Tactical Map</h2>
        <span>LOCAL_ENU_V1 · METERS · ORIGIN = START MARKER</span>
      </div>
      <div className="mc-map__layers">
        {LAYERS.map(([k, label]) => (
          <button key={k} type="button" aria-pressed={layers[k]} className={`mc-layer${layers[k] ? ' mc-layer--on' : ''}`} onClick={() => onToggle(k)}>
            <span className="mc-layer__dot" />{label}
          </button>
        ))}
      </div>
      <span className="mc-map__basemap">BASEMAP PROCEDURAL · ILLUSTRATIVE — MARKERS = ACCEPTED TELEMETRY</span>
    </div>
  )
}

export function MapLegend({ zoomText }: { zoomText: string }) {
  return (
    <div className="mc-legend">
      <div className="mc-legend__types">
        <span><HazardGlyph type="crater" />crater</span>
        <span><HazardGlyph type="rock" />rock</span>
        <span><HazardGlyph type="slope" />slope</span>
        <span><HazardGlyph type="unknown" />unknown</span>
      </div>
      <div className="mc-legend__note">outer ring = confidence · dashed disc = uncertainty radius</div>
      <div className="mc-legend__note">dashed trail = sequence gap, path unobserved</div>
      <div className="mc-legend__note">{zoomText}</div>
    </div>
  )
}

/** Blackout / stale / recovery banner. `top` is 120 px when the map is wider than 1100 px, else 160 px. */
export function OutageBanner({ banner, top }: { banner: NonNullable<BannerView>; top: number }) {
  return (
    <div className="mc-banner" role="alert" style={{ ...cssVars({ '--b-rgb': banner.rgb }), marginTop: top }}>
      <div className="mc-banner__head"><span className="mc-banner__kicker">{banner.kicker}</span><span className="mc-banner__timer">{banner.timer}</span></div>
      <span className="mc-banner__title">{banner.title}</span>
      <div className="mc-banner__rule" />
      <span className="mc-banner__l1">{banner.line1}</span>
      <span className="mc-banner__l2">{banner.line2}</span>
    </div>
  )
}

type NavProps = { cursorText: string; follow: boolean; onZoomIn: () => void; onZoomOut: () => void; onFit: () => void; onToggleFollow: () => void }
export function MapNav({ cursorText, follow, onZoomIn, onZoomOut, onFit, onToggleFollow }: NavProps) {
  return (
    <div className="mc-nav">
      <div className="mc-nav__cursor">{cursorText}</div>
      <div className="mc-nav__zoom">
        <button type="button" aria-label="Zoom in" onClick={onZoomIn}>+</button>
        <button type="button" aria-label="Zoom out" onClick={onZoomOut}>−</button>
        <button type="button" aria-label="Fit all" title="Fit trail and hazards" onClick={onFit}>FIT</button>
      </div>
      <button type="button" aria-pressed={follow} className={`mc-follow${follow ? ' mc-follow--on' : ''}`} onClick={onToggleFollow}>
        {follow ? '◎ FOLLOWING ROVER' : '◎ FOLLOW ROVER'}
      </button>
    </div>
  )
}
