// Walking with the camera: the rear camera fills the screen, floor chevrons point the way of the current step, its
// next room floats ahead, and the next-move card sits at the bottom. Same step index as the card on the plan
// (one route, one position in it). The Core takes "next / back / repeat" (handled in BuildingScreen) and sends
// anything else to the Guide with the current frame; "Where am I?" sends the frame on its own, and the Guide reads
// signs and room numbers in it. No positioning: the chevrons follow the step's turn, not a tracked heading.

import { ScanEye, Volume2, VolumeX, X } from 'lucide-react'
import { useEffect, useState, type RefObject } from 'react'
import type { GuideStep } from '../api'
import { Core } from './Core'
import { grabFrame } from './frame'
import type { Message, VoiceView } from './Guide'
import { NextMove } from './NextMove'
import type { RouteTrack } from './tracking'
import type { Position } from './useTracking'

type Props = {
  steps: GuideStep[]
  index: number
  lengthM: number | null
  profile: string | null
  voice: VoiceView
  /** the latest Guide answer or note, shown as a caption */
  answer: Message | undefined
  pending: boolean
  muted: boolean
  /** the camera's video element: BuildingScreen grabs a frame from it when a spoken question goes to the Guide */
  video: RefObject<HTMLVideoElement | null>
  onIndex: (index: number) => void
  /** live tracking, when it is on */
  position: Position | null
  track: RouteTrack | null
  onMute: () => void
  onWhereAmI: (photo: string | undefined) => void
  onClose: () => void
}

export function CameraWalk({ steps, index, lengthM, profile, voice, answer, pending, muted, video, onIndex, position, track, onMute, onWhereAmI, onClose }: Props) {
  const [camera, setCamera] = useState<'starting' | 'on' | 'off'>('starting')
  const [checkedAt, setCheckedAt] = useState<number | null>(null)
  const [now, setNow] = useState(() => Date.now())
  const step = steps[index]

  useEffect(() => {
    let stream: MediaStream | null = null
    let cancelled = false
    const start = async () => {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error('no camera API')
      const media = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 } }, audio: false })
      if (cancelled) return media.getTracks().forEach((track) => track.stop())
      stream = media
      if (video.current) video.current.srcObject = media
      setCamera('on')
    }
    start().catch(() => !cancelled && setCamera('off'))
    return () => {
      cancelled = true
      stream?.getTracks().forEach((track) => track.stop())
    }
  }, [video])

  // the "checked … s ago" chip counts while it is on screen
  useEffect(() => {
    if (checkedAt === null) return
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [checkedAt])

  useEffect(() => {
    const keys = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLElement && event.target.closest('input, textarea')) return
      if (event.key === 'Escape') onClose()
      else if (event.key === 'ArrowRight') onIndex(Math.min(steps.length - 1, index + 1))
      else if (event.key === 'ArrowLeft') onIndex(Math.max(0, index - 1))
    }
    addEventListener('keydown', keys)
    return () => removeEventListener('keydown', keys)
  }, [index, steps.length, onIndex, onClose])

  if (!step) return null
  const working = answer?.role === 'guide' && answer.live
  const running = working ? (answer.steps ?? []).findLast((item) => item.state === 'running') : undefined
  const ago = checkedAt === null ? 0 : Math.max(0, Math.round((now - checkedAt) / 1000))

  return (
    <div className="camera-walk" role="dialog" aria-modal="true" aria-label={`Walking directions, step ${index + 1} of ${steps.length}`}>
      <video ref={video} className={camera === 'on' ? 'on' : ''} autoPlay playsInline muted />
      {camera !== 'on' && <p className="cam-note">{camera === 'starting' ? 'Starting the camera…' : 'Camera unavailable. The directions still work.'}</p>}

      <Chevrons turn={step.kind === 'arrive' ? 'arrive' : step.turn} />
      {step.kind !== 'arrive' && (
        <p className="cam-tag" key={index}>
          {step.kind === 'connector' ? step.via : step.to}
          {step.metres > 0 && ` · ${step.metres} m`}
        </p>
      )}

      <header className="hud-top cam-top">
        <button type="button" className="hud-btn" onClick={onClose} aria-label="Close the camera">
          <X size={19} />
        </button>
        <div className="hud-place">
          <h1>
            Step {index + 1} of {steps.length}
          </h1>
          <p>Camera guidance</p>
        </div>
        <button type="button" className="hud-btn" onClick={onMute} aria-pressed={muted} aria-label={muted ? 'Read the steps aloud' : 'Stop reading the steps aloud'}>
          {muted ? <VolumeX size={18} /> : <Volume2 size={18} />}
        </button>
      </header>
      {checkedAt !== null && <p className="cam-fix">Camera view checked · {ago < 2 ? 'just now' : `${ago} s ago`}</p>}

      <div className="cam-bottom">
        {/* the route's own answer is the card below; other answers (e.g. "Where am I?") show here */}
        {(working || (answer && !(answer.role === 'guide' && answer.route))) && (
          <div className="cam-caption" aria-live="polite">
            {working ? (
              <p className="who">Guide · {running?.label ?? 'looking'}</p>
            ) : answer?.role === 'guide' ? (
              <p className="said">{answer.text.split('\n')[0]}</p>
            ) : answer?.role === 'note' ? (
              <p className="said warn">{answer.text}</p>
            ) : null}
          </div>
        )}
        <NextMove steps={steps} index={index} lengthM={lengthM} profile={profile} onIndex={onIndex} onClose={onClose} inline position={position} track={track} />
        <div className="dock">
          <span className="hud-side ghost" aria-hidden="true" />
          <Core state={voice.state} level={voice.level} busy={pending} size="small" hold={voice.holdToTalk} onHold={voice.hold} onListen={voice.listen} onFinish={voice.finish} onStop={voice.stop} />
          <button
            type="button"
            className="hud-side"
            disabled={pending}
            onClick={() => {
              setCheckedAt(Date.now())
              setNow(Date.now())
              onWhereAmI(grabFrame(video.current))
            }}
            aria-label="Where am I? Check the camera view"
            title="Where am I?"
          >
            <ScanEye size={20} />
          </button>
        </div>
        <p className="core-hint">Say next, back, repeat, or ask anything</p>
      </div>
    </div>
  )
}

/** Chevrons on the floor, in perspective, bending the way of the step's turn. */
function Chevrons({ turn }: { turn: GuideStep['turn'] | 'arrive' }) {
  if (turn === 'arrive') return null
  const bend = turn === 'left' ? -1 : turn === 'right' ? 1 : 0 // further chevrons swing and lean into the turn
  return (
    <svg className={`cam-chevrons ${turn}`} viewBox="0 0 340 300" preserveAspectRatio="xMidYMax meet" aria-hidden="true">
      <g fill="none" strokeLinecap="round" strokeLinejoin="round">
        {CHEVRONS.map(([y, w, apex, stroke, opacity], at) => (
          <polyline
            key={at}
            points={`${170 - w},${y} 170,${y - apex} ${170 + w},${y}`}
            strokeWidth={stroke}
            opacity={opacity}
            transform={bend ? `translate(${bend * at * at * 5} 0) rotate(${bend * at * 10} 170 ${y})` : undefined}
          />
        ))}
      </g>
    </svg>
  )
}

// [y, half width, apex height, stroke, opacity], near to far: a floor seen from standing height
const CHEVRONS = [
  [286, 70, 36, 20, 0.95],
  [222, 58, 32, 14, 0.8],
  [170, 48, 28, 10, 0.62],
  [128, 40, 24, 7, 0.46],
  [94, 33, 20, 5, 0.32],
] as const
