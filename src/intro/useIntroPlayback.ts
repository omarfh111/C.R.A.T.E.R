import { useCallback, useEffect, useState } from 'react'

const SESSION_KEY = 'crater:intro-started:v1'

function hasStartedInThisTab(): boolean {
  try {
    return window.sessionStorage.getItem(SESSION_KEY) === '1'
  } catch {
    return false
  }
}

function markStartedInThisTab(): void {
  try {
    window.sessionStorage.setItem(SESSION_KEY, '1')
  } catch {
    // An unavailable storage API must not block the intro or dashboard.
  }
}

export function useIntroPlayback() {
  const [introVisible, setIntroVisible] = useState(() => !hasStartedInThisTab())
  const [introRun, setIntroRun] = useState(0)
  const [handoffStarted, setHandoffStarted] = useState(false)

  useEffect(() => {
    if (introVisible) markStartedInThisTab()
    // Mark initial playback as soon as it starts, including before completion.
    // Replay does not change the tab's storage state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const startHandoff = useCallback(() => setHandoffStarted(true), [])
  const completeIntro = useCallback(() => {
    setIntroVisible(false)
    setHandoffStarted(false)
  }, [])
  const replayIntro = useCallback(() => {
    setIntroRun((run) => run + 1)
    setHandoffStarted(false)
    setIntroVisible(true)
  }, [])

  return { introVisible, introRun, handoffStarted, startHandoff, completeIntro, replayIntro }
}
