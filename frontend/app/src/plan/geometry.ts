// Plan → merged three.js geometry for one floor, built as a clay cutaway model: floor fills (vertex colours,
// recoloured in place for selection and states), a shallow slab edge under the floor, solid walls at their real
// thickness (core/floorplan.py `wall_solids`, toned by kind) cut low so every room stays visible, soft contact shadows along the wall feet, threshold strips in the doorways, hairline symbols (stair treads, lift
// crosses), and furniture as rough coloured models (furniture.ts). Scene frame = y-up, centred on the
// plan's `center`, with the floor at Y = 0: X = x - cx, Z = -y - cz.

import * as THREE from 'three'
import type { Plan, PlanSpace, PlanWall } from '../api'
import { furnitureGeometry, type FurnitureIndex } from './furniture'
import { categoryOf, type PlanPalette } from './palette'
import type { PlanSettings } from './settings'

export const WALL_M = 0.16
export const WALL_CUT_M = 0.85
const SLAB_M = 0.32
const AO_M = 0.55
const TREAD_M = 0.32
/** half depth of a doorway's threshold strip, across the wall */
const THRESHOLD_M = 0.16
/** how far past a doorless opening's ends to look for the wall it is cut into, and its dash length */
const OPENING_WALL_PROBE_M = 0.25
const OPENING_DASH_M = 0.18
const EDGE_DEG = 25
/** lift of a floor fill over the space it is mapped inside (a lobby zone in a hall, a stairwell in a corridor), so
 * the two coplanar fills do not fight; below the contact shadows */
const NESTED_LIFT_M = 0.002
/** lift of the stripes drawn where two spaces overlap: over both fills, below the contact shadows */
const OVERLAP_LIFT_M = 0.003
const LIFT = new Set(['lift'])
const STAIR = new Set(['stair', 'stairwell'])
/** wall body tone per kind, as a factor on the clay colour: the shell reads heaviest, partitions lightest */
const WALL_TONE: Record<PlanWall['kind'], number> = { exterior: 0.78, structural: 0.9, partition: 1 }

export type FloorGeometry = {
  fills: THREE.BufferGeometry
  slab: THREE.BufferGeometry
  walls: THREE.BufferGeometry
  shade: THREE.BufferGeometry
  lines: THREE.BufferGeometry
  /** wall centre lines, for drawing this floor as a faint ghost above or below another */
  outline: THREE.BufferGeometry
  /** threshold strips marking the doorways (vertex-coloured: doorway, entrance, closed) */
  doors: THREE.BufferGeometry
  /** crisp outlines of walls, steps and furniture (the edges of an architectural model) */
  wallEdges: THREE.BufferGeometry
  furnitureEdges: THREE.BufferGeometry
  /** soft shadows under furniture, same alpha shader as the wall contact shadows */
  contact: THREE.BufferGeometry
  furniture: THREE.BufferGeometry
  furnitureIndex: FurnitureIndex
  /** space id → [first vertex, vertex count] in `fills` */
  /** per space: its vertex ranges in `fills` (its floor, plus its stripes where it overlaps another space) */
  ranges: Map<string, [number, number][]>
}

export const toScene = (plan: Plan, x: number, y: number): [number, number] => [x - plan.center[0], -y - plan.center[1]]
export const fromScene = (plan: Plan, X: number, Z: number): [number, number] => [X + plan.center[0], -(Z + plan.center[1])]

type Look = Pick<PlanSettings, 'wallHeight' | 'colours'>

/** A space's floor colour under the chosen colour mode. */
export function fillOf(palette: PlanPalette, space: PlanSpace, colours: PlanSettings['colours']) {
  const category = categoryOf(space.type, space.room_type)
  if (colours === 'clay') return category === 'walk' ? palette.fills.walk : palette.clayFloor
  if (category === 'walk' || category === 'core') return palette.fills[category]
  // every room its own colour: the hue family comes from what the room is for, and each room turns it a little
  // (stable per room id), so two offices side by side still read as two rooms
  const color = new THREE.Color(palette.fills[category])
  const hsl = { h: 0, s: 0, l: 0 }
  color.getHSL(hsl)
  const n = roomHash(space.id)
  color.setHSL((hsl.h + (n - 0.5) * 0.26 + 1) % 1, Math.min(1, hsl.s * (0.85 + n * 0.4)), hsl.l + (roomHash(space.id + '/l') - 0.5) * 0.05)
  return '#' + color.getHexString()
}

/** Stable 0..1 number per string (FNV-1a). */
function roomHash(text: string) {
  let h = 2166136261
  for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 16777619)
  return ((h >>> 0) % 1000) / 1000
}

export function buildFloors(plan: Plan, palette: PlanPalette, look: Look): FloorGeometry[] {
  return plan.floors.map((_, index) => buildFloor(plan, index, palette, look))
}

function buildFloor(plan: Plan, floor: number, palette: PlanPalette, look: Look): FloorGeometry {
  const spaces = plan.spaces.filter((space) => space.floor === floor)

  // ---- floor fills
  const positions: number[] = []
  const colors: number[] = []
  const indices: number[] = []
  const ranges = new Map<string, [number, number][]>()
  const color = new THREE.Color()
  const nested = (space: PlanSpace) => spaces.some((other) =>
    other.area_m2 > space.area_m2 && contains(other.polygon, space.label[0], space.label[1]))
  for (const space of spaces) {
    const lift = nested(space) ? NESTED_LIFT_M : 0
    const contour = space.polygon.map(([x, y]) => new THREE.Vector2(x, y))
    if (THREE.ShapeUtils.isClockWise(contour)) contour.reverse()
    const triangles = THREE.ShapeUtils.triangulateShape(contour, [])
    const first = positions.length / 3
    color.set(fillOf(palette, space, look.colours))
    for (const point of contour) {
      const [X, Z] = toScene(plan, point.x, point.y)
      positions.push(X, lift, Z)
      colors.push(color.r, color.g, color.b)
    }
    for (const [a, b, c] of triangles) indices.push(first + a, first + c, first + b)
    ranges.set(space.id, [[first, contour.length]])
  }
  // where two spaces overlap the floor belongs to both: stripes in their two colours
  const byId = new Map(spaces.map((space) => [space.id, space]))
  for (const stripe of plan.overlaps?.[floor] ?? []) {
    const space = byId.get(stripe.space)
    if (!space) continue
    const [outer, ...holes] = stripe.rings.map((ring) => ring.map(([x, y]) => new THREE.Vector2(x, y)))
    if (THREE.ShapeUtils.isClockWise(outer)) outer.reverse()
    for (const hole of holes) if (!THREE.ShapeUtils.isClockWise(hole)) hole.reverse()
    const triangles = THREE.ShapeUtils.triangulateShape(outer, holes)
    const points = [outer, ...holes].flat()
    const first = positions.length / 3
    color.set(fillOf(palette, space, look.colours))
    for (const point of points) {
      const [X, Z] = toScene(plan, point.x, point.y)
      positions.push(X, OVERLAP_LIFT_M, Z)
      colors.push(color.r, color.g, color.b)
    }
    for (const [a, b, c] of triangles) indices.push(first + a, first + c, first + b)
    ranges.get(space.id)?.push([first, points.length])
  }
  // access mode: spaces this viewer may not enter, outline only, in one dark neutral (no label, furniture or
  // selection: they are not in plan.spaces, so nothing else draws or picks them)
  const restricted = (plan.restricted ?? []).filter((shape) => shape.floor === floor && shape.polygon.length > 2)
  color.set(palette.restricted)
  for (const shape of restricted) {
    const contour = shape.polygon.map(([x, y]) => new THREE.Vector2(x, y))
    if (THREE.ShapeUtils.isClockWise(contour)) contour.reverse()
    const first = positions.length / 3
    for (const point of contour) {
      const [X, Z] = toScene(plan, point.x, point.y)
      positions.push(X, 0, Z)
      colors.push(color.r, color.g, color.b)
    }
    for (const [a, b, c] of THREE.ShapeUtils.triangulateShape(contour, [])) indices.push(first + a, first + c, first + b)
  }
  const fills = new THREE.BufferGeometry()
  fills.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
  fills.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3))
  fills.setIndex(indices)
  fills.computeVertexNormals()

  // ---- slab edge: every outline dropped SLAB_M (inner duplicates hide under the floor)
  const slab = new Quads()
  for (const space of [...spaces, ...restricted]) {
    const points = space.polygon.map(([x, y]) => toScene(plan, x, y))
    for (let i = 0; i < points.length; i++) {
      const [ax, az] = points[i]
      const [bx, bz] = points[(i + 1) % points.length]
      slab.quad([ax, 0, az], [bx, 0, bz], [bx, -SLAB_M, bz], [ax, -SLAB_M, az])
    }
  }

  // ---- walls: the solid wall pieces extruded to the cut height, each tinted by its kind;
  // contact shadow: a strip on the floor along both sides of every room outline, dark at the wall and fading out
  // (the part under a wall is hidden by it)
  const H = look.wallHeight
  const walls = wallSolids(plan, plan.wall_solids?.[floor] ?? segmentWalls(plan.walls[floor] ?? []), H, palette.clay)
  const shade = { positions: [] as number[], alphas: [] as number[] }
  for (const [x1, y1, x2, y2] of plan.walls[floor] ?? []) {
    const [ax, az] = toScene(plan, x1, y1)
    const [bx, bz] = toScene(plan, x2, y2)
    const length = Math.hypot(bx - ax, bz - az)
    if (length < 1e-4) continue
    const nx = -(bz - az) / length
    const nz = (bx - ax) / length
    for (const side of [1, -1]) {
      const far = AO_M * side
      const c: [number, number] = [bx + nx * far, bz + nz * far]
      const d: [number, number] = [ax + nx * far, az + nz * far]
      shade.positions.push(ax, 0.004, az, bx, 0.004, bz, c[0], 0.004, c[1], ax, 0.004, az, c[0], 0.004, c[1], d[0], 0.004, d[1])
      shade.alphas.push(1, 1, 0, 1, 0, 0)
    }
  }
  // ---- hairlines
  const line: number[] = []
  const segment = (x1: number, y1: number, x2: number, y2: number) => {
    const [ax, az] = toScene(plan, x1, y1)
    const [bx, bz] = toScene(plan, x2, y2)
    line.push(ax, 0.006, az, bx, 0.006, bz)
  }
  // ---- stairs: no 3D steps (they read badly in the cutaway); a stairwell shows tread lines on its floor
  for (const space of spaces) {
    if (!(space.type === 'stair' || STAIR.has(space.room_type))) continue
    treads(space, (x1, y1, x2, y2) => {
      const [ax, az] = toScene(plan, x1, y1)
      const [bx, bz] = toScene(plan, x2, y2)
      line.push(ax, 0.006, az, bx, 0.006, bz)
    })
  }

  // ---- doors: the data has no swing or hinge, so no leaf; each doorway gets a flat threshold strip across the wall
  // gap, as wide as the door: entrances in accent blue, a closed door in red, every other doorway soft blue
  const doors = new Quads()
  const closed = new Set(plan.closed ?? [])
  const doorway = new THREE.Color(palette.door)
  const entrance = new THREE.Color(palette.entrance)
  const red = new THREE.Color(palette.materials.red)
  for (const opening of plan.openings) {
    if (opening.floor !== floor) continue
    const angle = (opening.angle * Math.PI) / 180
    const u = [Math.cos(angle), Math.sin(angle)]
    const half = opening.width_m / 2
    const corner = (along: number, across: number) =>
      toScene(plan, opening.position[0] + u[0] * along - u[1] * across, opening.position[1] + u[1] * along + u[0] * across)
    // a doorless opening is no door: one cut into a wall gets the drafting convention for an opening, a dashed
    // hairline across the gap; one that only splits an open plan (kitchen ↔ living room, corridor ↔ corridor) gets
    // nothing, so the floor simply runs on. Closed, it is a barrier like any closed door.
    if (opening.kind === 'opening' && !closed.has(opening.id)) {
      const reach = half + OPENING_WALL_PROBE_M
      const inWall = [reach, -reach].some((along) =>
        wallNear(plan.walls[floor] ?? [], opening.position[0] + u[0] * along, opening.position[1] + u[1] * along))
      if (inWall) {
        for (let a = -half; a < half; a += OPENING_DASH_M * 2) {
          const b = Math.min(half, a + OPENING_DASH_M)
          segment(opening.position[0] + u[0] * a, opening.position[1] + u[1] * a, opening.position[0] + u[0] * b, opening.position[1] + u[1] * b)
        }
      }
      continue
    }
    const colour = closed.has(opening.id) ? red : opening.entrance ? entrance : doorway
    doors.prism([corner(-half, THRESHOLD_M), corner(half, THRESHOLD_M), corner(half, -THRESHOLD_M), corner(-half, -THRESHOLD_M)], 0, 0.012, colour)
  }

  const shadeGeometry = new THREE.BufferGeometry()
  shadeGeometry.setAttribute('position', new THREE.Float32BufferAttribute(shade.positions, 3))
  shadeGeometry.setAttribute('alpha', new THREE.Float32BufferAttribute(shade.alphas, 1))

  for (const space of spaces) symbols(space, segment)
  const lines = new THREE.BufferGeometry()
  lines.setAttribute('position', new THREE.Float32BufferAttribute(line, 3))

  const ghost: number[] = []
  for (const [x1, y1, x2, y2] of plan.walls[floor] ?? []) {
    const [ax, az] = toScene(plan, x1, y1)
    const [bx, bz] = toScene(plan, x2, y2)
    ghost.push(ax, 0, az, bx, 0, bz)
  }
  const outline = new THREE.BufferGeometry()
  outline.setAttribute('position', new THREE.Float32BufferAttribute(ghost, 3))

  // ---- furniture
  const { geometry: furniture, index: furnitureIndex, contact } = furnitureGeometry(
    plan.assets.filter((asset) => asset.floor === floor),
    new Map(spaces.map((space) => [space.id, space.polygon])),
    (x, y) => toScene(plan, x, y),
    palette.materials,
  )

  const wallGeometry = walls
  return {
    fills,
    slab: slab.geometry(),
    walls: wallGeometry,
    shade: shadeGeometry,
    lines,
    outline,
    doors: doors.geometry(),
    wallEdges: new THREE.EdgesGeometry(wallGeometry, EDGE_DEG),
    furnitureEdges: new THREE.EdgesGeometry(furniture, EDGE_DEG),
    contact,
    furniture,
    furnitureIndex,
    ranges,
  }
}

/** A backend without `wall_solids`: a WALL_M box on every outline segment, extended by half a thickness so corners
 * close (the old look, double where drawn sources leave a gap between rooms). */
function segmentWalls(segments: [number, number, number, number][]): PlanWall[] {
  const half = WALL_M / 2
  return segments.flatMap(([x1, y1, x2, y2]) => {
    const length = Math.hypot(x2 - x1, y2 - y1)
    if (length < 1e-4) return []
    const ux = ((x2 - x1) / length) * half
    const uy = ((y2 - y1) / length) * half
    const ring: [number, number][] = [
      [x1 - ux - uy, y1 - uy + ux],
      [x2 + ux - uy, y2 + uy + ux],
      [x2 + ux + uy, y2 + uy - ux],
      [x1 - ux + uy, y1 - uy - ux],
    ]
    return [{ kind: 'partition' as const, rings: [ring] }]
  })
}

/** Wall pieces as prisms from the floor to `height`: a triangulated top (holes kept) and a side face per ring edge,
 * flat-shaded with a vertex colour per kind. */
function wallSolids(plan: Plan, pieces: PlanWall[], height: number, clay: string) {
  const positions: number[] = []
  const colors: number[] = []
  const tone = new THREE.Color()
  for (const piece of pieces) {
    tone.set(clay).multiplyScalar(WALL_TONE[piece.kind] ?? 1)
    const rings = piece.rings.map((ring) => ring.map(([x, y]) => new THREE.Vector2(x, y)))
    if (rings.length === 0 || rings[0].length < 3) continue
    const [outer, ...holes] = rings
    if (THREE.ShapeUtils.isClockWise(outer)) outer.reverse()
    for (const hole of holes) if (!THREE.ShapeUtils.isClockWise(hole)) hole.reverse()
    const points = [outer, ...holes].flat()
    const vertex = (point: THREE.Vector2, y: number) => {
      const [X, Z] = toScene(plan, point.x, point.y)
      positions.push(X, y, Z)
      colors.push(tone.r, tone.g, tone.b)
    }
    for (const [a, b, c] of THREE.ShapeUtils.triangulateShape(outer, holes)) {
      vertex(points[a], height)
      vertex(points[c], height)
      vertex(points[b], height)
    }
    for (const ring of [outer, ...holes]) {
      for (let i = 0; i < ring.length; i++) {
        const p = ring[i]
        const q = ring[(i + 1) % ring.length]
        for (const [point, y] of [[p, 0], [q, 0], [q, height], [p, 0], [q, height], [p, height]] as const) vertex(point, y)
      }
    }
  }
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
  geometry.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3))
  geometry.computeVertexNormals()
  return geometry
}

/** Flat-shaded quads with their own normals (no shared vertices, so edges stay crisp), optionally vertex-coloured. */
class Quads {
  positions: number[] = []
  colors: number[] = []
  quad(a: number[], b: number[], c: number[], d: number[], color?: THREE.Color) {
    this.positions.push(...a, ...b, ...c, ...a, ...c, ...d)
    if (color) for (let i = 0; i < 6; i++) this.colors.push(color.r, color.g, color.b)
  }
  /** A vertical prism over a 4-corner footprint (scene x, z), from y0 to y1: top and four sides. */
  prism(base: [number, number][], y0: number, y1: number, color?: THREE.Color) {
    const at = (i: number, y: number) => [base[i % 4][0], y, base[i % 4][1]]
    this.quad(at(0, y1), at(1, y1), at(2, y1), at(3, y1), color)
    for (let i = 0; i < 4; i++) this.quad(at(i, y0), at(i + 1, y0), at(i + 1, y1), at(i, y1), color)
  }
  geometry() {
    const geometry = new THREE.BufferGeometry()
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(this.positions, 3))
    if (this.colors.length) geometry.setAttribute('color', new THREE.Float32BufferAttribute(this.colors, 3))
    geometry.computeVertexNormals()
    return geometry
  }
}

/** A cross through a lift car, clipped to the space outline so odd-shaped shafts keep it inside their walls. */
function symbols(space: PlanSpace, draw: (x1: number, y1: number, x2: number, y2: number) => void) {
  if (!(space.type === 'lift' || LIFT.has(space.room_type))) return
  const segment = (x1: number, y1: number, x2: number, y2: number) => {
    for (const [a, b] of clip(space.polygon, x1, y1, x2, y2)) {
      draw(x1 + (x2 - x1) * a, y1 + (y2 - y1) * a, x1 + (x2 - x1) * b, y1 + (y2 - y1) * b)
    }
  }
  const xs = space.polygon.map((p) => p[0])
  const ys = space.polygon.map((p) => p[1])
  const x0 = Math.min(...xs) + WALL_M
  const x1 = Math.max(...xs) - WALL_M
  const y0 = Math.min(...ys) + WALL_M
  const y1 = Math.max(...ys) - WALL_M
  if (x1 <= x0 || y1 <= y0) return
  segment(x0, y0, x1, y1)
  segment(x0, y1, x1, y0)
}

/** Tread lines across an odd-shaped stairwell (clipped to its outline), where a straight flight would not fit. */
function treads(space: PlanSpace, draw: (x1: number, y1: number, x2: number, y2: number) => void) {
  const xs = space.polygon.map((p) => p[0])
  const ys = space.polygon.map((p) => p[1])
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)]
  const alongX = x1 - x0 >= y1 - y0
  const count = Math.min(40, Math.floor((alongX ? x1 - x0 : y1 - y0) / TREAD_M))
  for (let i = 1; i < count; i++) {
    const t = i / count
    const [ax, ay, bx, by] = alongX ? [x0 + t * (x1 - x0), y0, x0 + t * (x1 - x0), y1] : [x0, y0 + t * (y1 - y0), x1, y0 + t * (y1 - y0)]
    for (const [a, b] of clip(space.polygon, ax, ay, bx, by)) draw(ax + (bx - ax) * a, ay + (by - ay) * a, ax + (bx - ax) * b, ay + (by - ay) * b)
  }
}

/** Parts [t0, t1] of the segment p→q that lie inside the polygon. */
function clip(polygon: [number, number][], px: number, py: number, qx: number, qy: number): [number, number][] {
  const ts = [0, 1]
  const dx = qx - px
  const dy = qy - py
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const [ax, ay] = polygon[j]
    const [bx, by] = polygon[i]
    const ex = bx - ax
    const ey = by - ay
    const denominator = dx * ey - dy * ex
    if (Math.abs(denominator) < 1e-12) continue
    const t = ((ax - px) * ey - (ay - py) * ex) / denominator
    const u = ((ax - px) * dy - (ay - py) * dx) / denominator
    if (t > 0 && t < 1 && u >= 0 && u <= 1) ts.push(t)
  }
  ts.sort((a, b) => a - b)
  const parts: [number, number][] = []
  for (let k = 0; k + 1 < ts.length; k++) {
    const mid = (ts[k] + ts[k + 1]) / 2
    if (ts[k + 1] - ts[k] > 1e-6 && contains(polygon, px + dx * mid, py + dy * mid)) parts.push([ts[k], ts[k + 1]])
  }
  return parts
}

export function contains(polygon: [number, number][], x: number, y: number) {
  let hit = false
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const [xi, yi] = polygon[i]
    const [xj, yj] = polygon[j]
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) hit = !hit
  }
  return hit
}

/** Recolour one space's vertices in a floor's fill geometry. */
export function paintSpace(geometry: FloorGeometry, id: string, hex: string) {
  const ranges = geometry.ranges.get(id)
  if (!ranges) return
  const attribute = geometry.fills.getAttribute('color') as THREE.BufferAttribute
  const color = new THREE.Color(hex)
  for (const [first, count] of ranges) for (let i = first; i < first + count; i++) attribute.setXYZ(i, color.r, color.g, color.b)
  attribute.needsUpdate = true
}

/** Whether a wall segment ([x1, y1, x2, y2], plan metres) passes within WALL_M of a point. */
function wallNear(walls: [number, number, number, number][], x: number, y: number) {
  return walls.some(([x1, y1, x2, y2]) => {
    const dx = x2 - x1
    const dy = y2 - y1
    const t = Math.max(0, Math.min(1, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy || 1)))
    return Math.hypot(x - (x1 + dx * t), y - (y1 + dy * t)) < WALL_M
  })
}
