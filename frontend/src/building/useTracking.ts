// Live position along the current route, without positioning hardware: dead reckoning from the phone's motion
// sensor (a step is a peak in acceleration, STRIDE_M forward along the route) between fixes. A fix is a known
// place: the start, a door you confirmed (› or "next"), or a room the Guide placed you in from the camera. Every
// position carries its source and age, and is "stale" once it rests on many counted steps since the last fix.
// Counting never carries you past a ride (stairs, lift): you confirm the ride with "next".
// Without a motion sensor (desktop) only fixes move it. `?walk=sim` walks at a steady pace, for demos and checks.

import { useCallback, useEffect, useRef, useState } from 'react'
import type { RouteTrack } from './tracking'

const STRIDE_M = 0.7 // UNVERIFIED: a typical adult step; not calibrated per person
const STALE_M = 30 // counted metres since the last fix after which the position is shown as unsure
const PEAK = 11.8 // m/s² of |acceleration incl. gravity| that counts as a step (gravity ≈ 9.8)
const MIN_STEP_MS = 320
const SIM_STEP_MS = 550

export type FixSource = 'start' | 'door' | 'camera'
export type Position = {
  metres: number
  /** where the last fix came from, when, and how far has been counted since */
  source: FixSource
  fixAt: number
  counted: number
  stale: boolean
  sensor: 'motion' | 'sim' | 'none' | 'asking'
}

type Options = {
  track: RouteTrack | null
  /** a new route: tracking starts over */
  routeKey: number
  active: boolean
  /** the step on screen; when it changes from outside (›, "next", a segment) that door is a fix */
  step: number
  /** kinds of the steps, to stop counting at a ride */
  kinds: string[]
  onStep: (index: number) => void
}

export function useTracking({ track, routeKey, active, step, kinds, onStep }: Options) {
  const [position, setPosition] = useState<Position | null>(null)
  const own = useRef<number | null>(null) // a step change made by counting, not by the person
  const lastPeak = useRef(0)
  const onStepRef = useRef(onStep)
  useEffect(() => {
    onStepRef.current = onStep
  }, [onStep])

  const fix = useCallback(
    (metres: number, source: FixSource) =>
      setPosition((current) => ({ metres, source, fixAt: Date.now(), counted: 0, stale: false, sensor: current?.sensor ?? 'none' })),
    [],
  )

  // start (or restart for a new route) at the step on screen
  useEffect(() => {
    if (!active || !track) {
      setPosition(null)
      return
    }
    setPosition({ metres: track.starts[step] ?? 0, source: step === 0 ? 'start' : 'door', fixAt: Date.now(), counted: 0, stale: false, sensor: 'none' })
    // the step is read at start only; later changes are handled below
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, track, routeKey])

  // the person moved the step: that door is where they are now
  useEffect(() => {
    if (!active || !track) return
    if (own.current === step) {
      own.current = null
      return
    }
    fix(track.starts[step] ?? 0, step === 0 ? 'start' : 'door')
  }, [step, active, track, fix])

  const advance = useCallback(
    (metres: number) => {
      if (!track) return
      setPosition((current) => {
        if (!current) return current
        // never count past the start of the next ride: the ride itself is confirmed by the person
        const here = track.stepAt(current.metres)
        const ride = kinds.findIndex((kind, index) => index > here && kind === 'connector')
        const cap = ride >= 0 ? track.starts[ride] : track.total
        const next = Math.min(cap, current.metres + metres)
        const counted = current.counted + (next - current.metres)
        return { ...current, metres: next, counted, stale: counted > STALE_M }
      })
    },
    [track, kinds],
  )

  // the step follows the counted position
  useEffect(() => {
    if (!active || !track || !position) return
    const at = track.stepAt(position.metres)
    if (at > step && kinds[at - 1] !== 'connector') {
      own.current = at
      onStepRef.current(at)
    }
  }, [position, active, track, step, kinds])

  // motion sensor (or the steady walk of ?walk=sim)
  useEffect(() => {
    if (!active || !track) return
    if (new URLSearchParams(location.search).get('walk') === 'sim') {
      setPosition((current) => current && { ...current, sensor: 'sim' })
      const timer = setInterval(() => advance(STRIDE_M), SIM_STEP_MS)
      return () => clearInterval(timer)
    }
    if (typeof DeviceMotionEvent === 'undefined') return
    let seen = false
    const onMotion = (event: DeviceMotionEvent) => {
      const a = event.accelerationIncludingGravity
      if (!a || a.x === null || a.y === null || a.z === null) return
      if (!seen) {
        seen = true
        setPosition((current) => current && { ...current, sensor: 'motion' })
      }
      const magnitude = Math.hypot(a.x, a.y, a.z)
      const now = performance.now()
      if (magnitude > PEAK && now - lastPeak.current > MIN_STEP_MS) {
        lastPeak.current = now
        advance(STRIDE_M)
      }
    }
    addEventListener('devicemotion', onMotion)
    return () => removeEventListener('devicemotion', onMotion)
  }, [active, track, advance])

  /** The Guide placed you in a room of the route (from the camera): you are where the route enters it. */
  const fixAtStep = useCallback(
    (index: number, source: FixSource) => {
      if (!track) return
      const metres = track.starts[index] ?? 0
      own.current = index
      onStepRef.current(index)
      fix(metres, source)
    },
    [track, fix],
  )

  return { position, fixAtStep }
}

/** iOS asks before sharing motion; the question has to come from a tap. Elsewhere this resolves at once. */
export async function askForMotion(): Promise<boolean> {
  const ask = (DeviceMotionEvent as unknown as { requestPermission?: () => Promise<string> }).requestPermission
  if (typeof DeviceMotionEvent === 'undefined') return false
  if (!ask) return true
  try {
    return (await ask()) === 'granted'
  } catch {
    return false
  }
}
