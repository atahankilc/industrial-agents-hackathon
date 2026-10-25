// The route being followed, around the map instead of over it (variant B, 2026-10-25): a slim trip pill at the top
// (where to, how far is left, which step, the steps to jump between, camera / tracking, end), and one line with the
// one button that matters right now over the Guide's dock (Start → "I'm there" → Done, or Continue into the next
// building). The step itself is a callout pinned on the map where it is made (dev/StoryLayer `move` marker).

import { ArrowRight, Check, LocateFixed, Play, ScanEye, X } from 'lucide-react'
import type { GuideStep, NextBuilding } from '../api'
import { aboutM } from './NextMove'
import { metresLeft, type RouteTrack } from './tracking'
import type { Position } from './useTracking'

type TripProps = {
  steps: GuideStep[]
  index: number
  lengthM: number | null
  profile: string | null
  /** the step-by-step guide has started: the metres left count from this step */
  guiding: boolean
  next?: NextBuilding | null
  track?: RouteTrack | null
  position?: Position | null
  tracking?: boolean
  onTrack?: () => void
  onCamera?: () => void
  onIndex: (index: number) => void
  onClose: () => void
}

/** agent/tools find_route's profile text when nothing restricts the route; only other profiles are worth a word */
const DEFAULT_PROFILE = 'stairs allowed'

export function TripBar({ steps, index, lengthM, profile, guiding, next, track, position, tracking = false, onTrack, onCamera, onIndex, onClose }: TripProps) {
  const arrive = steps[steps.length - 1]
  const to = next ? next.name : arrive?.kind === 'arrive' && arrive.to_id !== 'outside' ? arrive.to : 'Way out'
  const left = metresLeft(steps, index, lengthM, guiding, track, position)
  return (
    <section className="trip-bar" aria-label="Route">
      <div className="trip-main">
        <span className="trip-to" title={to}>
          <ArrowRight size={14} strokeWidth={2.4} aria-hidden="true" />
          {to}
        </span>
        <span className="trip-meta">
          {left !== null && `${left < 1 ? 0 : aboutM(left)} m · `}
          {index + 1}/{steps.length}
          {profile && profile !== DEFAULT_PROFILE && ` · ${profile}`}
        </span>
        <ol className="trip-steps" aria-label="Steps">
          {steps.map((step, at) => (
            <li key={at}>
              <button
                type="button"
                className={at < index ? 'done' : at === index ? 'now' : ''}
                onClick={() => onIndex(at)}
                aria-label={`Step ${at + 1}: ${step.text}`}
                aria-current={at === index ? 'step' : undefined}
              />
            </li>
          ))}
        </ol>
      </div>
      <span className="trip-actions">
        {onTrack && (
          <button type="button" className="hud-icon track" onClick={onTrack} aria-pressed={tracking} aria-label={tracking ? 'Stop tracking me' : 'Track me along the route'} title={tracking ? 'Stop tracking' : 'Track me'}>
            <LocateFixed size={15} />
          </button>
        )}
        {onCamera && (
          <button type="button" className="hud-icon" onClick={onCamera} aria-label="Walk with the camera" title="Walk with the camera">
            <ScanEye size={15} />
          </button>
        )}
        <button type="button" className="hud-icon" onClick={onClose} aria-label="End directions" title="End directions">
          <X size={15} />
        </button>
      </span>
    </section>
  )
}

type BarProps = {
  steps: GuideStep[]
  index: number
  guiding: boolean
  next?: NextBuilding | null
  onStart: () => void
  onNext: () => void
  onFinish: () => void
  onContinue?: (next: NextBuilding) => void
}

/** The line over the dock: what to say (or tap) now. */
export function RouteBar({ steps, index, guiding, next, onStart, onNext, onFinish, onContinue }: BarProps) {
  const last = index >= steps.length - 1
  if (!guiding)
    return (
      <div className="route-bar">
        <p><i aria-hidden="true" />Say <em>“start”</em> and I'll walk you there.</p>
        <button type="button" className="route-go" onClick={onStart}>
          <Play size={14} />
          Start
        </button>
      </div>
    )
  if (last && next && onContinue)
    return (
      <div className="route-bar">
        <p><i aria-hidden="true" />You're at the exit.</p>
        <button type="button" className="route-go" onClick={() => onContinue(next)}>
          {next.name} · {next.outdoor_m} m
          <ArrowRight size={14} />
        </button>
      </div>
    )
  if (last)
    return (
      <div className="route-bar">
        <p><i aria-hidden="true" />You have arrived.</p>
        <button type="button" className="route-go" onClick={onFinish}>
          <Check size={14} />
          Done
        </button>
      </div>
    )
  return (
    <div className="route-bar">
      <p><i aria-hidden="true" />Reached it? Say <em>“I'm there”</em>.</p>
      <button type="button" className="route-go" onClick={onNext}>
        <Check size={14} />
        I'm there
      </button>
    </div>
  )
}
