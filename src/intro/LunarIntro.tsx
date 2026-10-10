import { useCallback, useEffect, useRef, useState } from 'react'
import { INTRO_DURATION_MS, mountLunarScene } from './lunarScene'
import './intro.css'

export const HANDOFF_DURATION_MS = 900

type Props = { onHandoffStart: () => void; onComplete: () => void; replay?: boolean }

export function LunarIntro({ onHandoffStart, onComplete, replay = false }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const finishTimer = useRef<number | undefined>(undefined)
  const exitingRef = useRef(false)
  const [fallback, setFallback] = useState(false)
  const [reducedMotion] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches)
  const [phase, setPhase] = useState(0)
  const [exiting, setExiting] = useState(false)

  const finish = useCallback(() => {
    if (exitingRef.current) return
    exitingRef.current = true
    setExiting(true)
    onHandoffStart()
    finishTimer.current = window.setTimeout(onComplete, reducedMotion ? 0 : HANDOFF_DURATION_MS)
  }, [onComplete, onHandoffStart, reducedMotion])

  useEffect(() => {
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = previous }
  }, [])

  useEffect(() => {
    if (reducedMotion || !canvasRef.current) return
    try {
      return mountLunarScene(canvasRef.current)
    } catch (error) {
      console.warn('Lunar WebGL scene unavailable; using local still image.', error)
      setFallback(true)
    }
  }, [reducedMotion])

  useEffect(() => {
    const timers = [
      window.setTimeout(() => setPhase(1), reducedMotion ? 0 : 850),
      window.setTimeout(() => setPhase(2), reducedMotion ? 0 : 1800),
      window.setTimeout(() => setPhase(3), reducedMotion ? 0 : 3350),
      window.setTimeout(finish, reducedMotion ? 700 : fallback ? 3600 : INTRO_DURATION_MS),
    ]
    return () => timers.forEach(clearTimeout)
  }, [fallback, finish, reducedMotion])

  useEffect(() => () => clearTimeout(finishTimer.current), [])

  return <section className={`lunar-intro ${fallback || reducedMotion ? 'lunar-intro--fallback' : ''} ${replay ? 'lunar-intro--replay' : ''} ${exiting ? 'lunar-intro--exiting' : ''}`} aria-label="C.R.A.T.E.R. lunar mission intro">
    {!reducedMotion && !fallback && <canvas ref={canvasRef} className="lunar-intro__canvas" aria-hidden="true" />}
    <div className="lunar-intro__atmosphere" aria-hidden="true" />
    <div className="lunar-intro__grid" aria-hidden="true" />
    <div className="lunar-intro__grain" aria-hidden="true" />
    <div className="lunar-intro__vignette" aria-hidden="true" />

    <div className="lunar-intro__topline">
      <div className="lunar-intro__mark"><span className="lunar-intro__mark-symbol" aria-hidden="true">◇</span><span>C.R.A.T.E.R.</span></div>
      <div className="lunar-intro__top-meta">LUNAR SURFACE<br />RECONNAISSANCE</div>
    </div>

    <div className="lunar-intro__body">
      <div className={`lunar-intro__eyebrow ${phase >= 1 ? 'is-visible' : ''}`}><span className="lunar-intro__eyebrow-line" />A NEW PERSPECTIVE ON THE UNKNOWN</div>
      <h2 className={`lunar-intro__title ${phase >= 2 ? 'is-visible' : ''}`}>BEYOND<br /><em>THE RIM.</em></h2>
      <div className={`lunar-intro__rule ${phase >= 2 ? 'is-visible' : ''}`} />
      <p className={`lunar-intro__description ${phase >= 3 ? 'is-visible' : ''}`}>LUNAR RECONNAISSANCE · MISSION CONTROL</p>
    </div>

    <div className="lunar-intro__bottomline">
      <span>EXPLORATION BEGINS AT THE EDGE.</span>
      <span className="lunar-intro__progress" aria-hidden="true"><i /></span>
    </div>
  </section>
}
