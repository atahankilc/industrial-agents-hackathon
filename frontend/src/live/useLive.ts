// The building's live world (backend/api/live/), polled about once a second while the building screen shows it (slower
// after errors). With the session it also re-checks the route on the map: a reroute, an alert or a suggestion comes
// back with the snapshot and is handed on once.

import { useEffect, useRef, useState } from 'react'
import { api, type LiveSnapshot } from '../api'

const POLL_MS = 1000
const POLL_MAX_MS = 15_000

export type LiveNews = Pick<LiveSnapshot, 'reroute' | 'alert' | 'suggestion'>

export function useLive(buildingId: string, sessionId: string | null, on: boolean, onNews: (news: LiveNews) => void) {
  const [live, setLive] = useState<LiveSnapshot | null>(null)
  const pollNow = useRef<() => void>(() => undefined)
  const news = useRef(onNews)
  useEffect(() => {
    news.current = onNews
  })

  useEffect(() => {
    if (!on) return
    let stopped = false
    let timer: ReturnType<typeof setTimeout> | undefined
    let wait = POLL_MS
    const poll = () => {
      clearTimeout(timer)
      api
        .live(buildingId, sessionId)
        .then((snapshot) => {
          if (stopped) return
          const { reroute, alert, suggestion, ...rest } = snapshot
          setLive(rest)
          if (reroute || alert || suggestion) news.current({ reroute, alert, suggestion })
          wait = POLL_MS
        })
        .catch(() => (wait = Math.min(wait * 2, POLL_MAX_MS)))
        .finally(() => {
          if (!stopped) timer = setTimeout(poll, wait)
        })
    }
    pollNow.current = poll
    poll()
    return () => {
      stopped = true
      clearTimeout(timer)
      pollNow.current = () => undefined
    }
  }, [buildingId, sessionId, on])

  // never another building's snapshot (the one before, until this building's first poll is back)
  return { live: on && live?.building === buildingId ? live : null, pollNow: () => pollNow.current() }
}
