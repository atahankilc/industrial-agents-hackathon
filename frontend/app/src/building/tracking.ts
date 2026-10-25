// Where along a route you are, as a point on the plan. The route line ([x, y, floor] in the plan frame, from
// core/routeline.py) and the route legs (metres per leg, one per Guide step) are in the same order; walking legs are
// spread over the line in proportion to their metres, rides (stairs, lifts) take no length on it. So "metres walked
// since the start" gives a point, the direction ahead, and the step you are in.

import type { RouteLeg } from '../api'

export type RouteTrack = {
  /** metres walked (route-model metres) at which each step starts; the last entry is the total */
  starts: number[]
  total: number
  at: (metres: number) => { at: [number, number]; floor: number; ahead: [number, number] }
  /** the step a walked distance falls in */
  stepAt: (metres: number) => number
  /** route-model metres → metres along the drawn line (what the route band measures, dev/StoryLayer routeRuns) */
  toLine: (metres: number) => number
}

export function routeTrack(line: [number, number, number][], legs: RouteLeg[]): RouteTrack | null {
  if (line.length < 2 || !legs.length) return null
  const starts: number[] = []
  let walked = 0
  for (const leg of legs) {
    starts.push(walked)
    if (leg.kind !== 'connector') walked += leg.distance_m
  }
  starts.push(walked)
  const total = walked

  // plan length along the line; a jump between floors is a ride and adds nothing
  const along: number[] = [0]
  for (let i = 1; i < line.length; i++) {
    const [x0, y0, f0] = line[i - 1]
    const [x1, y1, f1] = line[i]
    along.push(along[i - 1] + (f0 === f1 ? Math.hypot(x1 - x0, y1 - y0) : 0))
  }
  const length = along[along.length - 1]
  const scale = total > 0 ? length / total : 0

  const at = (metres: number) => {
    const target = Math.max(0, Math.min(length, metres * scale))
    let i = 1
    while (i < line.length - 1 && along[i] < target) i++
    // skip zero-length joints (floor jumps, repeated points) for the direction
    let j = i
    while (j < line.length - 1 && along[j] - along[j - 1] < 1e-6) j++
    const [x0, y0, f0] = line[j - 1]
    const [x1, y1] = line[j]
    const span = along[j] - along[j - 1]
    const t = span > 1e-6 ? Math.max(0, Math.min(1, (target - along[j - 1]) / span)) : 1
    const dx = x1 - x0
    const dy = y1 - y0
    const norm = Math.hypot(dx, dy) || 1
    return { at: [x0 + dx * t, y0 + dy * t] as [number, number], floor: f0, ahead: [dx / norm, dy / norm] as [number, number] }
  }

  const stepAt = (metres: number) => {
    let step = 0
    while (step + 1 < legs.length && metres >= starts[step + 1] - 1e-6) step++
    return step
  }

  const toLine = (metres: number) => Math.max(0, Math.min(length, metres * scale))

  return { starts, total, at, stepAt, toLine }
}
