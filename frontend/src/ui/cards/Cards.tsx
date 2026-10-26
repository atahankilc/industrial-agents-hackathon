// Structured pieces of a Guide reply: the route it drew, a change waiting for confirmation, the active profile.
// They only re-show what the backend returned (events, session summary); actions go back through the Guide as
// plain messages, so the conversation stays the single source of what happened.

import { useState } from 'react'
import type { RouteEvent, RouteLeg } from '../../api'
import { legText, TurnIcon } from '../TurnIcon'

export type RouteCardData = {
  key: number
  from: string
  to: string
  length: number | null
  profile: string
  floors: string[]
  legs: RouteLeg[]
  event: RouteEvent // replayed by "Show on map"
}

type RouteProps = { route: RouteCardData; onShow: () => void; onWalk: () => void }

export function RouteCard({ route, onShow, onWalk }: RouteProps) {
  const [open, setOpen] = useState(false)
  const steps = route.legs.filter((leg) => leg.kind !== 'arrive')
  return (
    <div className="card route-card">
      <div className="card-head">
        <span className="card-kicker">Route</span>
        {route.length !== null && <span className="card-figure">{Math.round(route.length)} m</span>}
      </div>
      <p className="route-ends">
        <span>{route.from}</span>
        <svg viewBox="0 0 16 8" width="16" height="8" aria-hidden="true"><path d="M0 4h14M11 1l3 3-3 3" fill="none" stroke="currentColor" strokeWidth="1.2" /></svg>
        <span>{route.to}</span>
      </p>
      <p className="card-meta">
        {steps.length} {steps.length === 1 ? 'step' : 'steps'}
        {route.floors.length > 1 && <> · {route.floors.join(' → ')}</>}
        {route.profile && <> · {route.profile}</>}
      </p>
      {open && (
        <ol className="legs">
          {route.legs.map((leg, index) => (
            <li key={index}>
              <TurnIcon leg={leg} size={16} />
              <span>{legText(leg, index === 0)}</span>
            </li>
          ))}
        </ol>
      )}
      <div className="card-actions">
        <button type="button" onClick={() => setOpen((on) => !on)} aria-expanded={open}>
          {open ? 'Hide steps' : 'Steps'}
        </button>
        <button type="button" onClick={onShow}>Show on map</button>
        {route.legs.length > 0 && (
          <button type="button" className="primary" onClick={onWalk}>
            <svg viewBox="0 0 16 16" width="13" height="13" aria-hidden="true"><path d="M2 5.5h2.2L5.5 4h5l1.3 1.5H14v7H2zM8 11a2 2 0 1 0 0-4 2 2 0 0 0 0 4z" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" /></svg>
            Walk with camera
          </button>
        )}
      </div>
    </div>
  )
}

type ChangeProps = { summary: string; busy: boolean; onApply: () => void; onDiscard: () => void }

export function ChangeCard({ summary, busy, onApply, onDiscard }: ChangeProps) {
  return (
    <div className="card change-card" role="group" aria-label="Change waiting for confirmation">
      <div className="card-head">
        <span className="card-kicker">Pending change</span>
      </div>
      <p>{summary}</p>
      <div className="card-actions">
        <button type="button" className="primary" disabled={busy} onClick={onApply}>Apply</button>
        <button type="button" disabled={busy} onClick={onDiscard}>Keep as is</button>
      </div>
    </div>
  )
}

export function AppliedNote({ text }: { text: string }) {
  return (
    <div className="applied">
      <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true"><path d="m3 8.5 3 3 7-7" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>
      <span>{text}</span>
    </div>
  )
}
