import type { TelemetryMode } from '../../telemetry/adapter'
import { MOCK_PRESETS, POSTURE_STYLE } from '../model/constants'
import type { Posture } from '../model/types'
import { cssVars } from './HazardGlyph'

export type DemoMenuProps = {
  open: boolean
  onToggle: () => void
  presetId: string
  onPick: (presetId: string) => void
  tickLabel: string
  showTick: boolean
}

type Props = {
  posture: Posture
  postureSub: string
  sourceMode: TelemetryMode
  utc: string
  /** ≥ 1560 px: show SCHEMA / frame chips and the posture caption. */
  wide: boolean
  onReplayIntro?: () => void
  /** MOCK only. Omit in LIVE mode — the DEMO control must not appear against real telemetry. */
  demo?: DemoMenuProps
}

export function MissionHeader({ posture, postureSub, sourceMode, utc, wide, onReplayIntro, demo }: Props) {
  const p = POSTURE_STYLE[posture]
  return (
    <header className="mc-header">
      <div className="mc-brand">
        <div className="mc-brand__mark"><span className="mc-brand__symbol" aria-hidden="true" /><span>C.R.A.T.E.R.</span></div>
        <span className="mc-brand__rule" />
        <div className="mc-brand__titles">
          <span className="mc-brand__title">MISSION CONTROL</span>
          <span className="mc-brand__sub">LUNAR SURFACE RECONNAISSANCE</span>
        </div>
      </div>

      <div className="mc-posture-wrap">
        <div className="mc-posture" role="status" aria-live="polite" style={cssVars({ '--p-rgb': p.rgb, '--p-color': p.color })}>
          <span className={`mc-posture__dot${posture === 'BLACKOUT' ? ' mc-posture__dot--blink' : ''}`} />
          <div className="mc-posture__text">
            <span className="mc-posture__label">{p.label}</span>
            <span className="mc-posture__sub">{postureSub}</span>
          </div>
        </div>
        {wide && <span className="mc-posture-note">COMMS POSTURE<br />DERIVED BY MISSION CONTROL</span>}
      </div>

      <div className="mc-header__right">
        <span className="mc-chip mc-chip--source"><span>SOURCE</span><strong>{sourceMode}</strong></span>
        {demo && <DemoMenu {...demo} />}
        {wide && <span className="mc-chip">SCHEMA v1</span>}
        {wide && <span className="mc-chip">LOCAL_ENU_V1 · m</span>}
        <span className="mc-clock"><span className="mc-clock__label">MC CLOCK UTC</span><span className="mc-clock__value">{utc}</span></span>
        {onReplayIntro && <button type="button" className="mc-replay" onClick={onReplayIntro}>↺ REPLAY INTRO</button>}
      </div>
    </header>
  )
}

/** DEMO · preview-only. Restarts the local mock adapter with VITE_MOCK_*-equivalent values. Never shown in LIVE mode. */
function DemoMenu({ open, onToggle, presetId, onPick, tickLabel, showTick }: DemoMenuProps) {
  return (
    <div className="mc-demo">
      <button type="button" className="mc-demo__toggle" onClick={onToggle} aria-expanded={open}>
        <strong>DEMO</strong>
        {showTick && <span className="mc-demo__tick">{tickLabel}</span>}
        <span className="mc-demo__caret">{open ? '▴' : '▾'}</span>
      </button>
      {open && (
        <div className="mc-demo__panel">
          <div className="mc-demo__head">
            <span className="mc-demo__title">DEMO · MOCK SESSION</span>
            <button type="button" className="mc-demo__close" onClick={onToggle}>CLOSE</button>
          </div>
          <div className="mc-demo__grid">
            {Object.entries(MOCK_PRESETS).map(([id, p]) => (
              <button key={id} type="button" className={`mc-demo__preset${id === presetId ? ' mc-demo__preset--on' : ''}`} onClick={() => onPick(id)}>
                <span>{id === presetId ? '● ' : ''}{p.label}</span>
                <span className="mc-demo__env">{p.env}</span>
              </button>
            ))}
          </div>
          <div className="mc-demo__note">Restarts the local mock adapter with these <em>VITE_MOCK_*</em> values and resets Mission Control state. Preview only. Does not control the rover radio simulator.</div>
        </div>
      )}
    </div>
  )
}
