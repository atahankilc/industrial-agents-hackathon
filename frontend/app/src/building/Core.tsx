// The Core: the Guide's presence and the main control. A thin ring with 32 radial ticks; while it listens or speaks
// the ticks follow the voice level (useVoice's `level` ref, read every frame), while it thinks an arc runs round the
// ring, and at rest it is still. Tap to talk (stops by itself on silence), hold to talk (release sends), tap while it
// speaks to stop it. No glow.

import { useEffect, useRef, type RefObject } from 'react'
import type { VoiceState } from '../voice/useVoice'

const TICKS = 32
const HOLD_MS = 350

type Props = {
  state: VoiceState
  level: RefObject<number>
  /** a typed question is being answered: show the thinking arc without the voice loop */
  busy: boolean
  size?: 'large' | 'small'
  onListen: () => void
  onFinish: () => void
  onStop: () => void
}

export function Core({ state, level, busy, size = 'large', onListen, onFinish, onStop }: Props) {
  const ticks = useRef<HTMLSpanElement>(null)
  const pressed = useRef(0)
  const mode = state === 'off' && busy ? 'thinking' : state

  // ticks move only while there is a voice to follow
  useEffect(() => {
    const root = ticks.current
    if (!root || (mode !== 'listening' && mode !== 'speaking')) return
    const bars = [...root.children] as HTMLElement[]
    let frame = 0
    const draw = (time: number) => {
      const value = Math.min(1, level.current ?? 0)
      bars.forEach((bar, index) => {
        const shape = 0.3 + 0.7 * Math.abs(Math.sin(time / 260 + index * 1.7) * Math.cos(index * 0.6 + time / 610))
        bar.style.setProperty('--h', (0.12 + value * shape).toFixed(3))
      })
      frame = requestAnimationFrame(draw)
    }
    frame = requestAnimationFrame(draw)
    return () => {
      cancelAnimationFrame(frame)
      bars.forEach((bar) => bar.style.removeProperty('--h'))
    }
  }, [mode, level])

  const label =
    mode === 'listening' ? 'Listening. Release or tap to send' : mode === 'speaking' ? 'Speaking. Tap to stop' : mode === 'thinking' ? 'Working' : 'Tap or hold to talk'

  return (
    <button
      type="button"
      className={`core ${size} ${mode}`}
      aria-label={label}
      title={label}
      disabled={mode === 'thinking'}
      onPointerDown={(event) => {
        if (event.button !== 0) return
        // a press that starts listening: a quick tap keeps listening until silence, a hold sends on release
        pressed.current = mode === 'off' ? performance.now() : 0
        if (mode === 'off') onListen()
      }}
      onPointerUp={() => {
        const startedHere = pressed.current > 0
        const held = startedHere ? performance.now() - pressed.current : 0
        pressed.current = 0
        if (mode === 'listening' && (!startedHere || held > HOLD_MS)) onFinish()
        else if (mode === 'speaking' && !startedHere) onStop()
      }}
      onKeyDown={(event) => {
        if (event.key !== 'Enter' && event.key !== ' ') return
        event.preventDefault()
        if (mode === 'off') onListen()
        else if (mode === 'listening') onFinish()
        else if (mode === 'speaking') onStop()
      }}
    >
      <span className="core-ring" />
      {mode === 'thinking' && <span className="core-arc" />}
      <span className="core-ticks" ref={ticks}>
        {Array.from({ length: TICKS }, (_, index) => (
          <i key={index} style={{ transform: `rotate(${(index * 360) / TICKS}deg)`, ['--rest' as string]: rest(index) }} />
        ))}
      </span>
      <span className="core-dot" />
    </button>
  )
}

/** A fixed, uneven resting pattern so the still ring reads as a voice, not a clock face. */
const rest = (index: number) => (0.15 + 0.5 * Math.abs(Math.sin(index * 1.7) * Math.cos(index * 0.6))).toFixed(2)
