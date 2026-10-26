// The living building's controls (backend/api/live.py): a round button on top of the plan's button column (a dot that
// turns orange while something blocks a walkway) opens the panel — every connected thing with what it reports and
// how, and the demo controls of the simulation: its speed, put a pallet or a forklift where you tap, block the
// route on the map, take away what was left behind. Notices about the route on the map (moved round something,
// blocked with no way round, a detour no longer needed) show as a card under the top line.

import { Ban, CircleAlert, Forklift, Gauge, Package, Pause, Play, Route, Sparkles, Trash2, X } from 'lucide-react'
import type { LiveDevice, LiveSnapshot } from '../api'
import { ago, KIND_ICON, stateLabel, tone } from './kinds'
import './live.css'

export type Placing = 'pallet' | 'forklift' | null
export type Notice = { kind: 'reroute' | 'alert' | 'suggestion'; message: string; key: number }

const SPEEDS = [1, 2, 4]

export function LiveButton({ live, open, onToggle, style }: { live: LiveSnapshot | null; open: boolean; onToggle: () => void; style: React.CSSProperties }) {
  const blocking = live?.devices.filter((item) => item.blocking).length ?? 0
  const count = live?.devices.length ?? 0
  return (
    <div className="live-corner" style={style}>
      <button
        type="button"
        className={`live-button${open ? ' open' : ''}${blocking ? ' blocking' : ''}`}
        aria-pressed={open}
        aria-label={`Live building: ${count} connected things${blocking ? `, ${blocking} blocking` : ''}`}
        title="Live building"
        onClick={onToggle}
      >
        <Gauge size={19} strokeWidth={2} />
        {live && <i aria-hidden="true">{count}</i>}
      </button>
    </div>
  )
}

export function LivePanel({ live, hasRoute, placing, focus, onPlace, onControl, onFocus, onClose, style }: {
  live: LiveSnapshot | null
  hasRoute: boolean
  placing: Placing
  focus: string | null
  onPlace: (kind: Placing) => void
  onControl: (action: 'speed' | 'pause' | 'resume' | 'clear' | 'block_route', value?: number) => void
  onFocus: (item: LiveDevice) => void
  onClose: () => void
  style: React.CSSProperties
}) {
  const devices = live?.devices ?? []
  const blocking = devices.filter((item) => item.blocking)
  const left = devices.filter((item) => item.state === 'left behind').length
  return (
    <section className="live-panel" style={style} aria-label="Live building">
      <header>
        <div>
          <h2>Live building</h2>
          <p>
            {devices.length} connected {devices.length === 1 ? 'thing' : 'things'}
            {blocking.length > 0 && <b> · {blocking.length} blocking</b>}
            {live?.simulated && <span className="sim">simulated</span>}
          </p>
        </div>
        <button type="button" className="hud-icon" onClick={onClose} aria-label="Close">
          <X size={17} strokeWidth={2.2} />
        </button>
      </header>

      <ul className="live-list">
        {devices.map((item) => {
          const Icon = KIND_ICON[item.kind]
          return (
            <li key={item.id}>
              <button type="button" className={`${tone(item)}${focus === item.id ? ' focused' : ''}`} onClick={() => onFocus(item)}>
                <span className="glyph"><Icon size={15} strokeWidth={2.1} /></span>
                <span className="what">
                  <b>{item.name.split(' · ')[0]}</b>
                  <small>
                    {item.blocking ? `blocks ${item.blocking.space}` : `${stateLabel(item.state)}${item.position.space ? ` · ${item.position.space}` : ''}`}
                  </small>
                </span>
                <span className="when">
                  <small>{item.link}</small>
                  <small>{ago(item.reported_ago_s)}</small>
                </span>
              </button>
            </li>
          )
        })}
        {devices.length === 0 && <li className="empty">Nothing reports in this building right now.</li>}
      </ul>

      <div className="live-tools" role="group" aria-label="Demo controls">
        <p className="live-hint">
          {placing ? `Tap the plan where the ${placing} goes.` : 'Demo: put something in the way and watch routes change.'}
        </p>
        <div className="row">
          <button type="button" className={`chip${placing === 'pallet' ? ' on' : ''}`} onClick={() => onPlace(placing === 'pallet' ? null : 'pallet')}>
            <Package size={15} strokeWidth={2} /> Drop pallet
          </button>
          <button type="button" className={`chip${placing === 'forklift' ? ' on' : ''}`} onClick={() => onPlace(placing === 'forklift' ? null : 'forklift')}>
            <Forklift size={15} strokeWidth={2} /> Park forklift
          </button>
          <button type="button" className="chip" disabled={!hasRoute} onClick={() => onControl('block_route')} title={hasRoute ? 'Pallets across the route on the map' : 'Ask for a route first'}>
            <Ban size={15} strokeWidth={2} /> Block my route
          </button>
          <button type="button" className="chip" disabled={!left} onClick={() => onControl('clear')}>
            <Trash2 size={15} strokeWidth={2} /> Pick up {left || ''}
          </button>
        </div>
        <div className="row speed" role="radiogroup" aria-label="Simulation speed">
          <button type="button" className="chip icon" onClick={() => onControl(live?.paused ? 'resume' : 'pause')} aria-label={live?.paused ? 'Resume' : 'Pause'}>
            {live?.paused ? <Play size={15} strokeWidth={2} /> : <Pause size={15} strokeWidth={2} />}
          </button>
          {SPEEDS.map((speed) => (
            <button key={speed} type="button" role="radio" aria-checked={live?.speed === speed} className={`chip${live?.speed === speed ? ' on' : ''}`} onClick={() => onControl('speed', speed)}>
              {speed}×
            </button>
          ))}
        </div>
      </div>
    </section>
  )
}

const NOTICE_ICON = { reroute: Route, alert: CircleAlert, suggestion: Sparkles }

export function LiveNotice({ notice, onTake, onClose, top }: { notice: Notice; onTake?: () => void; onClose: () => void; top: number }) {
  const Icon = NOTICE_ICON[notice.kind]
  return (
    <div className={`live-notice ${notice.kind}`} role="status" style={{ top }}>
      <Icon size={17} strokeWidth={2.2} aria-hidden="true" />
      <p>{notice.message}</p>
      {notice.kind === 'suggestion' && onTake && (
        <button type="button" className="take" onClick={onTake}>
          Take it
        </button>
      )}
      <button type="button" className="hud-icon" onClick={onClose} aria-label="Dismiss">
        <X size={15} strokeWidth={2.2} />
      </button>
    </div>
  )
}
