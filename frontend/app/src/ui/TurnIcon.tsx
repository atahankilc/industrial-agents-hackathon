// Arrow glyph for one route leg: turn left / right / straight / back, stairs or lift up / down, exit, arrive.

import type { RouteLeg } from '../api'

const PATHS: Record<string, string> = {
  straight: 'M12 20V5M6.5 10.5 12 5l5.5 5.5',
  left: 'M17 20v-6a4 4 0 0 0-4-4H6M10 5.5 5.5 10l4.5 4.5',
  right: 'M7 20v-6a4 4 0 0 1 4-4h7M14 5.5l4.5 4.5-4.5 4.5',
  back: 'M15 20V9a4 4 0 0 0-8 0v4M3.5 9.5 7 13l3.5-3.5',
  up: 'M4 20h4v-4h4v-4h4V8h4M14 4h6v6',
  down: 'M4 8h4v4h4v4h4v4h4M14 20h6v-6',
  lift_up: 'M6 3h12v18H6zM12 7l-3 3h6zM9 14h6',
  lift_down: 'M6 3h12v18H6zM12 17l-3-3h6zM9 10h6',
  exit: 'M10 4H5v16h5M14 8l4 4-4 4M18 12H9',
  arrive: 'M12 21s-6.5-5.6-6.5-11a6.5 6.5 0 0 1 13 0c0 5.4-6.5 11-6.5 11zM12 12.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5z',
}

export function legGlyph(leg: RouteLeg): string {
  if (leg.kind === 'arrive') return 'arrive'
  if (leg.kind === 'exit') return 'exit'
  if (leg.kind === 'connector') return `${leg.via_kind === 'lift' ? 'lift_' : ''}${leg.up ? 'up' : 'down'}`
  return leg.turn
}

export function TurnIcon({ leg, size = 18 }: { leg: RouteLeg; size?: number }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden="true" className="turn-icon">
      <path d={PATHS[legGlyph(leg)]} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

/** One plain sentence per leg, for the route card, the camera view and speech. */
export function legText(leg: RouteLeg, first: boolean): string {
  const metres = Math.round(leg.distance_m)
  const through = leg.via_kind === 'door' ? 'through the door' : leg.via_kind === 'entrance' ? 'through the entrance' : 'through the opening'
  if (leg.kind === 'arrive') return `You have arrived at ${leg.to}${leg.floor ? `, ${leg.floor}` : ''}.`
  if (leg.kind === 'exit') return `Walk about ${metres} m and leave the building ${through}.`
  if (leg.kind === 'connector') {
    const how = leg.via_kind === 'lift' ? `Take ${leg.via}` : `Use ${leg.via}`
    const span = leg.floors && leg.floors > 1 ? ` ${leg.floors} floors` : ''
    return `${how}${span} ${leg.up ? 'up' : 'down'} to ${leg.floor}.`
  }
  const turn = first || leg.turn === 'straight' ? '' : leg.turn === 'back' ? 'Turn around, then w' : `Turn ${leg.turn}, then w`
  return `${turn || 'W'}alk about ${metres} m ${through} into ${leg.to}.`
}
