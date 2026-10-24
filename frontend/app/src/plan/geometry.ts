// Plan → merged three.js geometry for one floor, built as a clay cutaway model: floor fills (vertex colours,
// recoloured in place for selection and states), a shallow slab edge under the floor, walls cut low so every room
// stays visible, soft contact shadows along the wall feet, hairline symbols (door swings, stair treads, lift
// crosses), and furniture as rough coloured models (furniture.ts). Scene frame = the viewer frame of
// core/pointcloud.py with the floor at Y = 0: X = x - cx, Z = -y - cz.

import * as THREE from 'three'
import type { Plan, PlanSpace } from '../api'
import { furnitureGeometry, type FurnitureIndex } from './furniture'
import { categoryOf, type PlanPalette } from './palette'
import type { PlanSettings } from './settings'

export const WALL_M = 0.16
export const WALL_CUT_M = 0.85
const SLAB_M = 0.32
const AO_M = 0.55
const ARC_STEPS = 10
const TREAD_M = 0.32
const DOOR_OPEN_DEG = 72
const DOOR_LEAF_M = 0.045
const DOOR_HEIGHT_M = 2.0
const EDGE_DEG = 25
const LIFT = new Set(['lift'])
const STAIR = new Set(['stair', 'stairwell'])

export type FloorGeometry = {
  fills: THREE.BufferGeometry
  slab: THREE.BufferGeometry
  walls: THREE.BufferGeometry
  shade: THREE.BufferGeometry
  lines: THREE.BufferGeometry
  /** wall centre lines, for drawing this floor as a faint ghost above or below another */
  outline: THREE.BufferGeometry
  /** open door leaves standing in their doorways */
  doors: THREE.BufferGeometry
  /** crisp outlines of walls, steps and furniture (the edges of an architectural model) */
  wallEdges: THREE.BufferGeometry
  furnitureEdges: THREE.BufferGeometry
  /** soft shadows under furniture, same alpha shader as the wall contact shadows */
  contact: THREE.BufferGeometry
  furniture: THREE.BufferGeometry
  furnitureIndex: FurnitureIndex
  /** space id → [first vertex, vertex count] in `fills` */
  ranges: Map<string, [number, number]>
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
  const ranges = new Map<string, [number, number]>()
  const color = new THREE.Color()
  for (const space of spaces) {
    const contour = space.polygon.map(([x, y]) => new THREE.Vector2(x, y))
    if (THREE.ShapeUtils.isClockWise(contour)) contour.reverse()
    const triangles = THREE.ShapeUtils.triangulateShape(contour, [])
    const first = positions.length / 3
    color.set(fillOf(palette, space, look.colours))
    for (const point of contour) {
      const [X, Z] = toScene(plan, point.x, point.y)
      positions.push(X, 0, Z)
      colors.push(color.r, color.g, color.b)
    }
    for (const [a, b, c] of triangles) indices.push(first + a, first + c, first + b)
    ranges.set(space.id, [first, contour.length])
  }
  const fills = new THREE.BufferGeometry()
  fills.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
  fills.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3))
  fills.setIndex(indices)
  fills.computeVertexNormals()

  // ---- slab edge: every outline dropped SLAB_M (inner duplicates hide under the floor)
  const slab = new Quads()
  for (const space of spaces) {
    const points = space.polygon.map(([x, y]) => toScene(plan, x, y))
    for (let i = 0; i < points.length; i++) {
      const [ax, az] = points[i]
      const [bx, bz] = points[(i + 1) % points.length]
      slab.quad([ax, 0, az], [bx, 0, bz], [bx, -SLAB_M, bz], [ax, -SLAB_M, az])
    }
  }

  // ---- walls: boxes WALL_M thick, WALL_CUT_M tall, extended by half a thickness so corners close;
  // contact shadow: a strip on the floor along both faces, dark at the wall and fading out
  const walls = new Quads()
  const shade = { positions: [] as number[], alphas: [] as number[] }
  const half = WALL_M / 2
  const H = look.wallHeight
  for (const [x1, y1, x2, y2] of plan.walls[floor] ?? []) {
    const [ax, az] = toScene(plan, x1, y1)
    const [bx, bz] = toScene(plan, x2, y2)
    const length = Math.hypot(bx - ax, bz - az)
    if (length < 1e-4) continue
    const ux = (bx - ax) / length
    const uz = (bz - az) / length
    const nx = -uz
    const nz = ux
    const sx = ax - ux * half
    const sz = az - uz * half
    const ex = bx + ux * half
    const ez = bz + uz * half
    const p = (x: number, z: number, side: number, y: number): [number, number, number] => [x + nx * half * side, y, z + nz * half * side]
    walls.quad(p(sx, sz, 1, H), p(ex, ez, 1, H), p(ex, ez, -1, H), p(sx, sz, -1, H)) // top
    walls.quad(p(sx, sz, 1, 0), p(ex, ez, 1, 0), p(ex, ez, 1, H), p(sx, sz, 1, H)) // face +n
    walls.quad(p(ex, ez, -1, 0), p(sx, sz, -1, 0), p(sx, sz, -1, H), p(ex, ez, -1, H)) // face -n
    walls.quad(p(sx, sz, -1, 0), p(sx, sz, 1, 0), p(sx, sz, 1, H), p(sx, sz, -1, H)) // start cap
    walls.quad(p(ex, ez, 1, 0), p(ex, ez, -1, 0), p(ex, ez, -1, H), p(ex, ez, 1, H)) // end cap
    for (const side of [1, -1]) {
      const near = half * side
      const far = (half + AO_M) * side
      const a: [number, number] = [ax + nx * near, az + nz * near]
      const b: [number, number] = [bx + nx * near, bz + nz * near]
      const c: [number, number] = [bx + nx * far, bz + nz * far]
      const d: [number, number] = [ax + nx * far, az + nz * far]
      shade.positions.push(a[0], 0.004, a[1], b[0], 0.004, b[1], c[0], 0.004, c[1], a[0], 0.004, a[1], c[0], 0.004, c[1], d[0], 0.004, d[1])
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

  // ---- doors: the leaf standing open at DOOR_OPEN_DEG into the side it swings to (same hinge and side as the
  // swing arc drawn on the floor)
  const doors = new Quads()
  for (const opening of plan.openings) {
    if (opening.floor !== floor || opening.kind === 'opening') continue
    const angle = (opening.angle * Math.PI) / 180
    const open = (DOOR_OPEN_DEG * Math.PI) / 180
    const u = [Math.cos(angle), Math.sin(angle)]
    const n = [-u[1] * opening.side, u[0] * opening.side]
    const d = [u[0] * Math.cos(open) + n[0] * Math.sin(open), u[1] * Math.cos(open) + n[1] * Math.sin(open)]
    const p = [(-d[1] * DOOR_LEAF_M) / 2, (d[0] * DOOR_LEAF_M) / 2]
    const w = opening.width_m * 0.96
    const hx = opening.position[0] - (u[0] * opening.width_m) / 2
    const hy = opening.position[1] - (u[1] * opening.width_m) / 2
    const corner = (along: number, side: number) => toScene(plan, hx + d[0] * along + p[0] * side, hy + d[1] * along + p[1] * side)
    doors.prism([corner(0, 1), corner(w, 1), corner(w, -1), corner(0, -1)], 0.01, Math.min(H, DOOR_HEIGHT_M))
  }

  const shadeGeometry = new THREE.BufferGeometry()
  shadeGeometry.setAttribute('position', new THREE.Float32BufferAttribute(shade.positions, 3))
  shadeGeometry.setAttribute('alpha', new THREE.Float32BufferAttribute(shade.alphas, 1))

  for (const opening of plan.openings) {
    if (opening.floor !== floor || opening.kind === 'opening') continue
    const angle = (opening.angle * Math.PI) / 180
    const ux = Math.cos(angle)
    const uy = Math.sin(angle)
    const nx = -uy * opening.side
    const ny = ux * opening.side
    const w = opening.width_m
    const hx = opening.position[0] - (ux * w) / 2
    const hy = opening.position[1] - (uy * w) / 2
    segment(hx, hy, hx + nx * w, hy + ny * w) // the leaf, standing open
    let px = hx + nx * w
    let py = hy + ny * w
    for (let step = 1; step <= ARC_STEPS; step++) {
      const t = (step / ARC_STEPS) * (Math.PI / 2)
      const qx = hx + (nx * Math.cos(t) + ux * Math.sin(t)) * w
      const qy = hy + (ny * Math.cos(t) + uy * Math.sin(t)) * w
      segment(px, py, qx, qy)
      px = qx
      py = qy
    }
  }
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

  const wallGeometry = walls.geometry()
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

/** Flat-shaded quads with their own normals (no shared vertices, so edges stay crisp). */
class Quads {
  positions: number[] = []
  quad(a: number[], b: number[], c: number[], d: number[]) {
    this.positions.push(...a, ...b, ...c, ...a, ...c, ...d)
  }
  /** A vertical prism over a 4-corner footprint (scene x, z), from y0 to y1: top and four sides. */
  prism(base: [number, number][], y0: number, y1: number) {
    const at = (i: number, y: number) => [base[i % 4][0], y, base[i % 4][1]]
    this.quad(at(0, y1), at(1, y1), at(2, y1), at(3, y1))
    for (let i = 0; i < 4; i++) this.quad(at(i, y0), at(i + 1, y0), at(i + 1, y1), at(i, y1))
  }
  geometry() {
    const geometry = new THREE.BufferGeometry()
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(this.positions, 3))
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
  const range = geometry.ranges.get(id)
  if (!range) return
  const attribute = geometry.fills.getAttribute('color') as THREE.BufferAttribute
  const color = new THREE.Color(hex)
  for (let i = range[0]; i < range[0] + range[1]; i++) attribute.setXYZ(i, color.r, color.g, color.b)
  attribute.needsUpdate = true
}
