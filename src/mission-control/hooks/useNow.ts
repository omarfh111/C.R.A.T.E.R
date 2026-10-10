import { useEffect, useState } from 'react'

/** Wall clock at a fixed cadence. Drives information age, freshness and timers (100 ms in the approved design). */
export function useNow(periodMs = 100) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), periodMs)
    return () => clearInterval(id)
  }, [periodMs])
  return now
}

/** Live viewport width (used to hide secondary header chips below 1560 / 1240 px). */
export function useViewportWidth() {
  const [w, setW] = useState(() => window.innerWidth)
  useEffect(() => {
    const on = () => setW(window.innerWidth)
    window.addEventListener('resize', on)
    on()
    return () => window.removeEventListener('resize', on)
  }, [])
  return w
}
