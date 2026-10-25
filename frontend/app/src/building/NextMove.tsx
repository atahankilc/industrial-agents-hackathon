// The next move of a route, as big as a road sign: the arrow, the metres, where it takes you and what marks the door.
// Built only from the Guide's own steps (route event `steps`, core/directions.guidance), so the card and the spoken
// directions never disagree. One segment per step below: tap the card (or ›) for the next one, a segment to jump.
// While tracking (useTracking), the metres count down from your position, and a last line says where that position
// comes from and how old it is; it turns amber when it rests on many counted steps.
// Before the guide starts the card offers Start (the map shows the whole route meanwhile); once started, "I'm there"
// moves on, and a route that goes on in a nearby building ends in Continue.

import { ArrowRight, Check, ChevronLeft, ChevronRight, LocateFixed, Play, ScanEye, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { GuideStep, NextBuilding } from '../api'
import { TurnIcon } from '../ui/TurnIcon'
import type { RouteTrack } from './tracking'
import type { Position } from './useTracking'

type Props = {
  steps: GuideStep[]
  index: number
  lengthM: number | null
  profile: string | null
  onIndex: (index: number) => void
  onClose: () => void
  /** walk this route with the camera (CameraWalk); absent inside the camera view itself */
  onCamera?: () => void
  /** placed by its parent (the camera view's bottom stack) instead of under the top line */
  inline?: boolean
  /** live tracking: the toggle (on the plan only), and the position with the route it is measured on */
  tracking?: boolean
  onTrack?: () => void
  position?: Position | null
  track?: RouteTrack | null
  /** the step-by-step guide: started or not, and how to start it (absent: no guide, e.g. in the camera view) */
  guiding?: boolean
  onStart?: () => void
  /** the route goes on in a nearby building */
  next?: NextBuilding | null
  onContinue?: (next: NextBuilding) => void
  /** the guide reached the last step and the user confirms they are there: the route is done */
  onFinish?: () => void
}

export function NextMove({ steps, index, lengthM, profile, onIndex, onClose, onCamera, inline = false, tracking = false, onTrack, position, track, guiding = false, onStart, next, onContinue, onFinish }: Props) {
  const step = steps[index]
  if (!step) return null
  const last = steps.length - 1
  const go = (to: number) => onIndex(Math.max(0, Math.min(last, to)))
  const live = position && track ? position : null
  // metres still to walk in this step, and on the whole route, from the tracked position
  const stepLeft = live && track ? Math.max(0, (track.starts[index + 1] ?? track.total) - live.metres) : null
  const routeLeft = live && track ? Math.max(0, track.total - live.metres) : null
  const metres = stepLeft !== null ? (stepLeft < 1 ? 0 : aboutM(stepLeft)) : step.metres

  return (
    <section className={`next-move${inline ? ' inline' : ''}`} aria-label="Directions" aria-live="polite">
      <header>
        <span>
          Step {index + 1} / {steps.length}
          {routeLeft !== null ? ` · ${routeLeft < 1 ? 0 : aboutM(routeLeft)} m left` : lengthM !== null && ` · ${aboutM(lengthM)} m`}
          {profile && profile !== DEFAULT_PROFILE && ` · ${profile}`}
        </span>
        <span className="nav">
          {onTrack && (
            <button type="button" className="hud-icon track" onClick={onTrack} aria-pressed={tracking} aria-label={tracking ? 'Stop tracking me' : 'Track me along the route'} title={tracking ? 'Stop tracking' : 'Track me'}>
              <LocateFixed size={16} />
            </button>
          )}
          {onCamera && (
            <button type="button" className="hud-pill" onClick={onCamera} aria-label="Walk with the camera">
              <ScanEye size={15} />
              Camera
            </button>
          )}
          {(inline || !onTrack) && (
            <>
              <button type="button" className="hud-icon" onClick={() => go(index - 1)} disabled={index === 0} aria-label="Previous step">
                <ChevronLeft size={16} />
              </button>
              <button type="button" className="hud-icon" onClick={() => go(index + 1)} disabled={index === last} aria-label="Next step">
                <ChevronRight size={16} />
              </button>
            </>
          )}
          {!inline && (
            <button type="button" className="hud-icon" onClick={onClose} aria-label="End directions">
              <X size={16} />
            </button>
          )}
        </span>
      </header>
      {/* keyed by the step, so a new step slides in (hud.css .next-move .move) */}
      <button key={index} type="button" className={`move ${step.kind}`} onClick={() => go(index + 1)} disabled={index === last} aria-label={step.text}>
        <span className="arrow">
          <TurnIcon leg={step} size={30} stroke={2.2} />
        </span>
        <span className="what">
          {step.metres > 0 && (
            <b className="metres">
              {metres}
              <small>m</small>
            </b>
          )}
          <span className="where">{title(step)}</span>
          {detail(step) && <span className="by">{detail(step)}</span>}
        </span>
      </button>
      <ol className="segments" aria-label="Steps">
        {steps.map((item, at) => (
          <li key={at}>
            <button
              type="button"
              className={at < index ? 'done' : at === index ? 'now' : ''}
              onClick={() => go(at)}
              aria-label={`Step ${at + 1}: ${item.text}`}
              aria-current={at === index ? 'step' : undefined}
            />
          </li>
        ))}
      </ol>
      {(onStart || next || onFinish) && (
        <div className="guide-actions">
          {onStart && !guiding && (
            <button type="button" className="primary" onClick={onStart}>
              <Play size={15} />
              Start — guide me step by step
            </button>
          )}
          {onStart && guiding && index < last && (
            <button type="button" className="primary" onClick={() => go(index + 1)}>
              <Check size={15} />
              I'm there — next step
            </button>
          )}
          {onFinish && guiding && index === last && !next && (
            <button type="button" className="primary" onClick={onFinish}>
              <Check size={15} />
              I'm here — done
            </button>
          )}
          {next && onContinue && (guiding ? index === last : true) && (
            <button type="button" className={guiding ? 'primary' : ''} onClick={() => onContinue(next)}>
              Continue in {next.name} · {next.outdoor_m} m {next.heading}
              <ArrowRight size={15} />
            </button>
          )}
        </div>
      )}
      {live && <Fix position={live} />}
    </section>
  )
}

const SOURCE = { start: 'from the start', door: 'from the door you confirmed', camera: 'from the camera' } as const

/** Where the tracked position comes from, how old that fix is, and how much has been counted on top of it. */
function Fix({ position }: { position: Position }) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [])
  const seconds = Math.max(0, Math.round((now - position.fixAt) / 1000))
  const age = seconds < 2 ? 'just now' : seconds < 90 ? `${seconds} s ago` : `${Math.round(seconds / 60)} min ago`
  const counted = Math.round(position.counted)
  return (
    <p className={`fix ${position.stale ? 'stale' : ''}`} role="status">
      {position.stale
        ? `Unsure: ${counted} m counted since the last fix. Show the camera a sign, or tap the step you are on.`
        : position.sensor === 'none'
          ? `Position ${SOURCE[position.source]} · ${age} · no motion sensor: tap the card at each door`
          : `Position ${SOURCE[position.source]} · ${age}${counted ? ` · +${counted} m counted` : ''}${position.sensor === 'sim' ? ' (simulated walk)' : ''}`}
    </p>
  )
}

/** agent/tools find_route's profile text when nothing restricts the route; only other profiles are worth a word */
const DEFAULT_PROFILE = 'stairs allowed'

const TURN = { left: 'Turn left', right: 'Turn right', back: 'Turn around', straight: '' } as const

export function title(step: GuideStep): string {
  const turn = TURN[step.turn]
  if (step.kind === 'arrive') return step.to_id === 'outside' ? 'You are outside' : `${step.to}`
  if (step.kind === 'exit') return turn ? `${turn} and leave the building` : 'Leave the building'
  if (step.kind === 'connector') {
    const span = step.floors && step.floors > 1 ? ` ${step.floors} floors` : ''
    return `${step.via ?? 'Stairs'} ${step.up ? 'up' : 'down'}${span} to ${step.floor}`
  }
  return turn ? `${turn} into ${step.to}` : `Into ${step.to}`
}

export function detail(step: GuideStep): string | null {
  if (step.kind === 'arrive') return step.to_id === 'outside' ? null : `You have arrived${step.floor ? ` · ${step.floor}` : ''}`
  if (step.kind === 'connector') return null
  if (step.landmark) return `by the ${step.landmark}`
  return step.door ? `through the ${step.door}` : null
}

/** How the Guide says a total distance (core/directions.about_m): whole metres below 10, steps of 5, of 10 from 100. */
export function aboutM(metres: number): number {
  const step = metres < 10 ? 1 : metres < 100 ? 5 : 10
  return Math.max(1, Math.floor(metres / step + 0.5) * step)
}
