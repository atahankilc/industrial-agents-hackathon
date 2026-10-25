// Plan geometry for the Edit mode, in building metres (x right, y up). The SVG draws (x, -y).

export type XY = [number, number]

export const GRID_M = 0.05
export const SNAP_RADIUS_M = 0.25
export const SAME_POINT_M = 0.01

export const round3 = (value: number) => Math.round(value * 1000) / 1000

export function samePoint(a: XY, b: XY, tolerance = SAME_POINT_M) {
  return Math.hypot(a[0] - b[0], a[1] - b[1]) <= tolerance
}

/** Nearest existing vertex within `radius`, else the point on the `grid`. */
export function snap(xy: XY, vertices: XY[], grid = GRID_M, radius = SNAP_RADIUS_M): XY {
  let best: XY | null = null
  let bestDistance = radius
  for (const vertex of vertices) {
    const distance = Math.hypot(vertex[0] - xy[0], vertex[1] - xy[1])
    if (distance <= bestDistance) {
      best = vertex
      bestDistance = distance
    }
  }
  if (best) return [best[0], best[1]]
  return [round3(Math.round(xy[0] / grid) * grid), round3(Math.round(xy[1] / grid) * grid)]
}

/** Closest point to `p` on the segment a–b, and its distance. */
export function projectOnSegment(p: XY, a: XY, b: XY): { point: XY; distance: number } {
  const dx = b[0] - a[0]
  const dy = b[1] - a[1]
  const length2 = dx * dx + dy * dy
  const t = length2 === 0 ? 0 : Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length2))
  const point: XY = [a[0] + t * dx, a[1] + t * dy]
  return { point, distance: Math.hypot(p[0] - point[0], p[1] - point[1]) }
}

/** The polygon edge closest to `p`: its endpoints and the projected point. */
export function nearestEdge(p: XY, polygon: XY[]): { a: XY; b: XY; point: XY; distance: number } {
  let best = { a: polygon[0], b: polygon[1 % polygon.length], point: polygon[0], distance: Infinity }
  polygon.forEach((a, i) => {
    const b = polygon[(i + 1) % polygon.length]
    const hit = projectOnSegment(p, a, b)
    if (hit.distance < best.distance) best = { a, b, point: hit.point, distance: hit.distance }
  })
  return best
}

export function area(polygon: XY[]) {
  let sum = 0
  polygon.forEach((a, i) => {
    const b = polygon[(i + 1) % polygon.length]
    sum += a[0] * b[1] - b[0] * a[1]
  })
  return Math.abs(sum) / 2
}

export function centroid(polygon: XY[]): XY {
  const n = polygon.length
  return [polygon.reduce((s, p) => s + p[0], 0) / n, polygon.reduce((s, p) => s + p[1], 0) / n]
}

export function bounds(polygons: XY[][]) {
  const xs = polygons.flat().map((p) => p[0])
  const ys = polygons.flat().map((p) => p[1])
  return { minX: Math.min(...xs), maxX: Math.max(...xs), minY: Math.min(...ys), maxY: Math.max(...ys) }
}

/** SVG points attribute for a building-frame polygon (y flipped). */
export const svgPoints = (polygon: XY[]) => polygon.map(([x, y]) => `${x},${-y}`).join(' ')

/** Unit outward normal of each edge i → i+1, from the ring's orientation (core/edits.outward_normals). */
export function outwardNormals(polygon: XY[]): XY[] {
  let twice = 0
  polygon.forEach((a, i) => {
    const b = polygon[(i + 1) % polygon.length]
    twice += a[0] * b[1] - b[0] * a[1]
  })
  const sign = twice > 0 ? 1 : -1
  return polygon.map((a, i) => {
    const b = polygon[(i + 1) % polygon.length]
    const length = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1
    return [(sign * (b[1] - a[1])) / length, (-sign * (b[0] - a[0])) / length]
  })
}

/** Ray-casting point-in-polygon test. */
export function inside(p: XY, polygon: XY[]) {
  let hit = false
  polygon.forEach((a, i) => {
    const b = polygon[(i + 1) % polygon.length]
    if (a[1] > p[1] !== b[1] > p[1] && p[0] < ((b[0] - a[0]) * (p[1] - a[1])) / (b[1] - a[1]) + a[0]) hit = !hit
  })
  return hit
}
