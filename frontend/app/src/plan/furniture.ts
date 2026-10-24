// Rough furniture models, built from boxes and octagonal prisms so every piece reads as what it is (a bed has a
// pillow and a headboard, a chair a back, a plant a pot and leaves) without loading any asset files. Each part is
// given in the piece's own footprint frame: x and z run -0.5..0.5 across the footprint's width and depth (the back
// of a piece is +z), y is metres above the floor. All pieces of a floor merge into one coloured geometry.

import * as THREE from 'three'
import type { PlanAsset } from '../api'

export type Material =
  | 'wood' | 'oak' | 'fabric' | 'cushion' | 'linen' | 'blanket' | 'ceramic' | 'metal' | 'dark' | 'steel'
  | 'leaf' | 'pot' | 'red' | 'screen' | 'books' | 'rack' | 'cardboard' | 'machine' | 'machineTop' | 'glass'

type Part = { shape: 'box' | 'cyl'; x: [number, number]; z: [number, number]; y: [number, number]; m: Material }
const box = (x0: number, x1: number, z0: number, z1: number, y0: number, y1: number, m: Material): Part => ({ shape: 'box', x: [x0, x1], z: [z0, z1], y: [y0, y1], m })
const cyl = (x0: number, x1: number, z0: number, z1: number, y0: number, y1: number, m: Material): Part => ({ shape: 'cyl', x: [x0, x1], z: [z0, z1], y: [y0, y1], m })
const L = -0.5
const R = 0.5

/** Four slim legs under a top, inset from the corners. */
const legs = (top: number, m: Material, inset = 0.06, size = 0.07): Part[] =>
  [[L + inset, L + inset + size], [R - inset - size, R - inset]].flatMap((x) =>
    [[L + inset, L + inset + size], [R - inset - size, R - inset]].map((z) => box(x[0], x[1], z[0], z[1], 0, top, m)),
  )

const table = (height: number, top: Material = 'oak', leg: Material = 'steel') => [box(L, R, L, R, height - 0.04, height, top), ...legs(height - 0.04, leg)]
const chair = (seat: Material = 'fabric') => [
  ...legs(0.42, 'steel', 0.1, 0.06),
  box(L + 0.06, R - 0.06, L + 0.06, R - 0.06, 0.42, 0.47, seat),
  box(L + 0.06, R - 0.06, 0.32, R - 0.04, 0.47, 0.86, seat),
]
const cabinet = (height: number, m: Material, top: Material = m) => [box(L, R, L, R, 0, height - 0.02, m), box(L, R, L, R, height - 0.02, height, top)]
const shelves = (height: number, levels: number, frame: Material, fill: Material) => {
  const parts: Part[] = [box(L, L + 0.06, L, R, 0, height, frame), box(R - 0.06, R, L, R, 0, height, frame), box(L, R, 0.42, R, 0, height, frame)]
  for (let i = 0; i <= levels; i++) {
    const y = (i / levels) * (height - 0.03)
    parts.push(box(L, R, L, R, y, y + 0.03, frame))
    if (i < levels) parts.push(box(L + 0.1, R - 0.1, L + 0.1, 0.4, y + 0.03, y + (height / levels) * 0.72, fill))
  }
  return parts
}
const bed = (blanket: Material = 'blanket') => [
  box(L, R, L, R, 0.08, 0.32, 'oak'),
  box(L + 0.03, R - 0.03, L + 0.02, R - 0.08, 0.32, 0.5, 'linen'),
  box(L + 0.03, R - 0.03, L + 0.02, 0.12, 0.5, 0.54, blanket),
  box(L + 0.1, R - 0.1, 0.22, 0.42, 0.5, 0.6, 'linen'),
  box(L, R, R - 0.06, R, 0.08, 0.95, 'oak'),
]
const machine = (height: number) => [
  box(L, R, L, R, 0, height * 0.55, 'machine'),
  box(L + 0.12, R - 0.12, L + 0.1, R - 0.15, height * 0.55, height, 'machineTop'),
  box(L + 0.2, R - 0.2, L - 0.02, L + 0.05, height * 0.3, height * 0.5, 'screen'),
]

const MODELS: Record<string, Part[]> = {
  chair: chair(),
  dining_chair: chair('oak'),
  outdoor_chair: chair('wood'),
  office_chair: [
    cyl(L + 0.05, R - 0.05, L + 0.05, R - 0.05, 0, 0.06, 'dark'),
    cyl(-0.06, 0.06, -0.06, 0.06, 0.06, 0.42, 'steel'),
    box(L + 0.06, R - 0.06, L + 0.06, R - 0.06, 0.42, 0.5, 'fabric'),
    box(L + 0.1, R - 0.1, 0.3, R - 0.06, 0.5, 0.98, 'fabric'),
  ],
  armchair: [box(L, R, L, R, 0.12, 0.42, 'cushion'), box(L, R, 0.28, R, 0.42, 0.8, 'cushion'), box(L, L + 0.16, L, R, 0.42, 0.6, 'cushion'), box(R - 0.16, R, L, R, 0.42, 0.6, 'cushion')],
  sofa: [box(L, R, L, R, 0.1, 0.42, 'cushion'), box(L, R, 0.24, R, 0.42, 0.8, 'cushion'), box(L, L + 0.08, L, R, 0.42, 0.62, 'cushion'), box(R - 0.08, R, L, R, 0.42, 0.62, 'cushion')],
  bench: [box(L, R, L, R, 0.4, 0.45, 'oak'), ...legs(0.4, 'steel', 0.04)],
  lecture_seating_row: [box(L, R, L, 0.1, 0.42, 0.47, 'fabric'), box(L, R, 0.1, 0.22, 0.47, 0.82, 'fabric'), box(L, R, 0.3, R, 0.72, 0.76, 'oak'), box(L, R, 0.22, 0.3, 0, 0.76, 'steel')],
  desk: [box(L, R, L, R, 0.7, 0.74, 'oak'), box(L, L + 0.05, L + 0.05, R - 0.05, 0, 0.7, 'steel'), box(R - 0.05, R, L + 0.05, R - 0.05, 0, 0.7, 'steel'), box(L + 0.3, R - 0.3, 0.3, 0.36, 0.74, 1.05, 'screen')],
  reception_desk: [box(L, R, L, R, 0, 1.05, 'oak'), box(L, R, L - 0.02, L + 0.08, 1.0, 1.1, 'oak')],
  seminar_table: table(0.74),
  meeting_table: table(0.74),
  dining_table: table(0.74),
  canteen_table: table(0.74),
  reading_table: table(0.74),
  outdoor_table: table(0.72, 'wood'),
  coffee_table: table(0.42),
  lab_bench: [box(L, R, L, R, 0, 0.86, 'ceramic'), box(L, R, L, R, 0.86, 0.92, 'dark'), box(L, R, 0.38, R, 0.92, 1.4, 'glass')],
  workbench: [box(L, R, L, R, 0.86, 0.92, 'oak'), ...legs(0.86, 'steel'), box(L, R, 0.42, R, 0.92, 1.5, 'steel')],
  assembly_station: [box(L, R, L, R, 0.86, 0.92, 'oak'), ...legs(0.86, 'steel'), box(L, R, 0.4, R, 0.92, 1.6, 'rack')],
  packing_station: [box(L, R, L, R, 0.86, 0.92, 'oak'), ...legs(0.86, 'steel'), box(L + 0.1, 0.0, L + 0.1, 0.1, 0.92, 1.2, 'cardboard')],
  inspection_bench: [box(L, R, L, R, 0, 0.9, 'steel'), box(L + 0.2, R - 0.2, L + 0.2, R - 0.2, 0.9, 1.25, 'machineTop')],
  lectern: [box(L + 0.15, R - 0.15, L + 0.15, R - 0.15, 0, 1.0, 'oak'), box(L, R, L, R, 1.0, 1.12, 'oak')],
  bed: bed(),
  single_bed: bed('cushion'),
  nightstand: cabinet(0.5, 'oak'),
  tv_stand: [...cabinet(0.5, 'oak'), box(L + 0.1, R - 0.1, 0.1, 0.18, 0.5, 1.1, 'screen')],
  wardrobe: cabinet(1.9, 'wood'),
  built_in_wardrobe: cabinet(2.0, 'linen'),
  bookshelf: shelves(1.8, 5, 'oak', 'books'),
  shelf: shelves(1.6, 4, 'wood', 'books'),
  paper_shelf: shelves(1.6, 5, 'steel', 'linen'),
  pallet_rack: shelves(2.2, 3, 'rack', 'cardboard'),
  filing_cabinet: cabinet(1.2, 'steel'),
  tool_cabinet: cabinet(1.1, 'red', 'steel'),
  chemical_cabinet: cabinet(1.8, 'rack'),
  locker: cabinet(1.8, 'steel'),
  shoe_cabinet: cabinet(1.0, 'oak'),
  coat_rack: [cyl(L + 0.2, R - 0.2, L + 0.2, R - 0.2, 0, 0.05, 'dark'), cyl(-0.05, 0.05, -0.05, 0.05, 0, 1.7, 'dark')],
  plant: [cyl(L + 0.2, R - 0.2, L + 0.2, R - 0.2, 0, 0.32, 'pot'), cyl(L, R, L, R, 0.32, 0.75, 'leaf'), cyl(L + 0.15, R - 0.15, L + 0.15, R - 0.15, 0.75, 1.0, 'leaf')],
  waste_basket: [cyl(L, R, L, R, 0, 0.4, 'dark')],
  toilet: [box(L + 0.1, R - 0.1, 0.22, R, 0, 0.78, 'ceramic'), cyl(L + 0.08, R - 0.08, L, 0.3, 0, 0.42, 'ceramic')],
  sink: [box(L, R, L, R, 0, 0.78, 'linen'), box(L, R, L, R, 0.78, 0.86, 'ceramic')],
  shower: [box(L, R, L, R, 0, 0.08, 'ceramic'), box(L, L + 0.03, L, R, 0.08, 1.1, 'glass'), box(L, R, R - 0.03, R, 0.08, 1.1, 'glass')],
  bathtub: [box(L, R, L, R, 0, 0.56, 'ceramic'), box(L + 0.08, R - 0.08, L + 0.08, R - 0.08, 0.5, 0.57, 'glass')],
  kitchen_counter: [box(L, R, L, R, 0, 0.86, 'linen'), box(L, R, L, R, 0.86, 0.9, 'dark')],
  serving_counter: [box(L, R, L, R, 0, 0.92, 'oak'), box(L, R, L, R, 0.92, 0.96, 'steel')],
  internal_stairs: [0, 1, 2, 3, 4, 5].map((i) => box(L, R, L + i / 6, L + (i + 1) / 6, 0, 0.18 * (i + 1), 'oak')),
  fridge: cabinet(1.8, 'ceramic'),
  stove: [box(L, R, L, R, 0, 0.88, 'steel'), box(L + 0.05, R - 0.05, L + 0.05, R - 0.05, 0.88, 0.9, 'dark')],
  dishwasher: cabinet(0.86, 'steel'),
  washing_machine: [box(L, R, L, R, 0, 0.85, 'ceramic'), cyl(L + 0.2, R - 0.2, L - 0.02, L + 0.02, 0.25, 0.65, 'glass')],
  microwave: [box(L, R, L, R, 0.9, 1.2, 'steel')],
  coffee_machine: [box(L, R, L, R, 0.9, 1.3, 'dark')],
  water_dispenser: [box(L, R, L, R, 0, 1.0, 'ceramic'), cyl(L + 0.15, R - 0.15, L + 0.15, R - 0.15, 1.0, 1.4, 'glass')],
  vending_machine: [box(L, R, L, R, 0, 1.8, 'dark'), box(L + 0.1, R - 0.3, L - 0.02, L + 0.02, 0.5, 1.6, 'glass'), box(R - 0.25, R - 0.1, L - 0.02, L + 0.02, 0.9, 1.1, 'red')],
  atm: [box(L, R, L, R, 0, 1.5, 'steel'), box(L + 0.2, R - 0.2, L - 0.02, L + 0.02, 1.0, 1.3, 'screen')],
  fire_extinguisher: [cyl(L + 0.15, R - 0.15, L + 0.15, R - 0.15, 0, 0.6, 'red')],
  defibrillator: [box(L, R, L, R, 1.0, 1.4, 'leaf')],
  eyewash_station: [cyl(-0.08, 0.08, -0.08, 0.08, 0, 1.0, 'leaf'), cyl(L, R, L, R, 1.0, 1.1, 'leaf')],
  hand_dryer: [box(L, R, L, R, 1.0, 1.3, 'ceramic')],
  electrical_panel: [box(L, R, L, R, 0.6, 1.8, 'steel')],
  whiteboard: [box(L, R, 0.35, R, 0.85, 1.9, 'ceramic'), box(L, R, L, R, 0.85, 0.9, 'steel')],
  projector_screen: [box(L, R, 0.4, R, 0.6, 2.0, 'ceramic')],
  display_screen: [box(L, R, 0.3, R, 0.8, 1.4, 'screen'), box(-0.05, 0.05, 0.35, R, 0, 0.8, 'dark')],
  projector: [box(L, R, L, R, 2.2, 2.35, 'dark')],
  multifunction_printer: [box(L, R, L, R, 0, 1.1, 'ceramic'), box(L + 0.1, R - 0.1, L + 0.1, R - 0.1, 1.1, 1.15, 'dark')],
  printer: [box(L, R, L, R, 0.75, 1.0, 'ceramic')],
  server_rack: [box(L, R, L, R, 0, 2.0, 'dark'), box(L + 0.06, R - 0.06, L - 0.01, L + 0.02, 0.1, 1.9, 'screen')],
  ups_unit: cabinet(1.0, 'dark'),
  microscope: [box(L + 0.2, R - 0.2, L + 0.2, R - 0.2, 0.9, 0.95, 'dark'), cyl(-0.12, 0.12, 0, 0.3, 0.95, 1.3, 'dark')],
  oscilloscope_station: [...table(0.74, 'oak'), box(L + 0.15, R - 0.15, 0.1, R - 0.05, 0.74, 1.0, 'screen')],
  soldering_station: [...table(0.86, 'oak'), box(L + 0.2, 0.0, 0.1, R - 0.1, 0.86, 1.0, 'dark')],
  welding_station: [...table(0.86, 'steel'), box(L, R, R - 0.04, R, 0.86, 1.8, 'red')],
  fume_hood: [box(L, R, L, R, 0, 0.9, 'ceramic'), box(L, R, 0.0, R, 0.9, 2.2, 'steel'), box(L + 0.05, R - 0.05, L, L + 0.04, 1.0, 1.7, 'glass')],
  pallet_jack: [box(L, R, -0.1, R, 0, 0.1, 'rack'), cyl(-0.06, 0.06, L, -0.3, 0.1, 1.1, 'dark')],
  forklift: [box(L, R, -0.1, R, 0, 1.0, 'rack'), box(L + 0.1, R - 0.1, -0.1, 0.35, 1.0, 2.1, 'glass'), box(L + 0.1, L + 0.2, L, -0.1, 0, 2.2, 'dark'), box(R - 0.2, R - 0.1, L, -0.1, 0, 2.2, 'dark')],
  forklift_charging_station: [box(L, R, L, R, 0, 1.4, 'leaf')],
  conveyor: [box(L, R, L, R, 0.7, 0.85, 'dark'), ...legs(0.7, 'steel')],
  '3d_printer': [box(L, R, L, R, 0, 0.6, 'dark'), box(L + 0.05, R - 0.05, L + 0.05, R - 0.05, 0.6, 1.2, 'glass')],
  hvac_unit: machine(2.0),
  boiler: [cyl(L, R, L, R, 0, 2.0, 'steel')],
  compressor: [box(L, R, L, R, 0, 0.9, 'rack'), cyl(L + 0.1, R - 0.1, L + 0.1, 0.0, 0.9, 1.3, 'steel')],
}

/** Model for a piece: its type's model, else a generic block by category (machines get a control panel). */
function model(asset: PlanAsset): Part[] {
  const known = MODELS[asset.type]
  if (known) return known
  if (asset.category === 'machine') return machine(1.9)
  if (asset.category === 'equipment') return cabinet(1.1, 'steel')
  if (asset.category === 'fixture') return cabinet(0.9, 'ceramic')
  return cabinet(0.8, 'oak')
}

const SIDES = 8

export type FurnitureIndex = { starts: number[]; ids: string[] }

/** Pieces that stand with their back to a wall. The data's rotation is right for most of them, but not for every
 * type (toilets and sinks point any way), so these are turned to put their back against the nearest wall. */
const AGAINST_WALL = new Set([
  'toilet', 'sink', 'bed', 'single_bed', 'wardrobe', 'built_in_wardrobe', 'bookshelf', 'shelf', 'paper_shelf', 'desk',
  'sofa', 'tv_stand', 'kitchen_counter', 'fridge', 'stove', 'dishwasher', 'washing_machine', 'whiteboard',
  'projector_screen', 'display_screen', 'vending_machine', 'lab_bench', 'fume_hood', 'locker', 'filing_cabinet',
  'tool_cabinet', 'chemical_cabinet', 'shoe_cabinet', 'nightstand', 'hand_dryer', 'electrical_panel',
  'eyewash_station', 'defibrillator', 'atm', 'water_dispenser', 'coffee_machine', 'microwave', 'serving_counter',
])
/** Seats face the nearest table within reach (their back away from it). */
const SEATS = new Set(['chair', 'dining_chair', 'office_chair', 'outdoor_chair', 'armchair'])
const TABLES = new Set([
  'desk', 'seminar_table', 'meeting_table', 'dining_table', 'canteen_table', 'reading_table', 'outdoor_table',
  'coffee_table', 'lab_bench', 'workbench', 'reception_desk', 'oscilloscope_station', 'soldering_station',
])
const SEAT_REACH_M = 1.6
/** Pieces that hang on a wall or sit on a counter cast no shadow on the floor. */
const OFF_FLOOR = new Set(['hand_dryer', 'whiteboard', 'projector', 'projector_screen', 'electrical_panel', 'defibrillator', 'microwave', 'coffee_machine', 'printer', 'microscope'])
const CONTACT_SPREAD_M = 0.22

type Footprint = { angle: number; width: number; depth: number }

/** Distance from p along direction d to the polygon outline. */
function rayToOutline(polygon: [number, number][], [px, py]: [number, number], [dx, dy]: [number, number]) {
  let best = Infinity
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const [ax, ay] = polygon[j]
    const [bx, by] = polygon[i]
    const ex = bx - ax
    const ey = by - ay
    const denominator = dx * ey - dy * ex
    if (Math.abs(denominator) < 1e-12) continue
    const t = ((ax - px) * ey - (ay - py) * ex) / denominator
    const u = ((ax - px) * dy - (ay - py) * dx) / denominator
    if (t > 0 && u >= 0 && u <= 1) best = Math.min(best, t)
  }
  return best
}

/** The model's angle (radians, about +Y in the scene) and footprint for a piece. A model's back is its +z side,
 * which lands on the building direction (sin φ, -cos φ) (scene Z = -y) for φ = rotation + 180°, i.e. rotation + 90°
 * counter-clockwise from +x: the side the data puts against the wall (checked on ~32k wall-standing assets).
 * Pieces in AGAINST_WALL or SEATS may turn by quarter turns (swapping width and depth on odd turns). */
function placement(asset: PlanAsset, room: [number, number][] | undefined, tables: PlanAsset[]): Footprint {
  const base = (asset.rotation_deg * Math.PI) / 180 + Math.PI
  const back = (turn: number): [number, number] => [Math.sin(base + turn * (Math.PI / 2)), -Math.cos(base + turn * (Math.PI / 2))]
  const footprint = (turn: number): Footprint => ({
    angle: base + turn * (Math.PI / 2),
    width: turn % 2 ? asset.size[1] : asset.size[0],
    depth: turn % 2 ? asset.size[0] : asset.size[1],
  })
  const turns = [0, 1, 2, 3]
  if (SEATS.has(asset.type)) {
    const [x, y] = asset.position
    const near = tables
      .map((table) => ({ table, distance: Math.hypot(table.position[0] - x, table.position[1] - y) }))
      .filter((item) => item.distance < SEAT_REACH_M)
      .sort((a, b) => a.distance - b.distance)[0]
    if (!near) return footprint(0)
    const away: [number, number] = [x - near.table.position[0], y - near.table.position[1]]
    return footprint(turns.reduce((best, turn) => {
      const score = (k: number) => back(k)[0] * away[0] + back(k)[1] * away[1]
      return score(turn) > score(best) ? turn : best
    }, 0))
  }
  if (room && AGAINST_WALL.has(asset.type)) {
    // the side whose edge is closest to a wall (distance from the centre minus half the size on that axis)
    const gap = (turn: number) => rayToOutline(room, asset.position, back(turn)) - footprint(turn).depth / 2
    return footprint(turns.reduce((best, turn) => (gap(turn) < gap(best) - 0.05 ? turn : best), 0))
  }
  return footprint(0)
}

/** All pieces of a floor as one non-indexed geometry with per-vertex colour; normals per face (flat). `index`
 * maps vertex ranges back to asset ids (piece k owns vertices starts[k] .. starts[k + 1]) for picking. */
export function furnitureGeometry(
  assets: PlanAsset[],
  rooms: Map<string, [number, number][]>,
  place: (x: number, y: number) => [number, number],
  colors: Record<Material, string>,
) {
  const index: FurnitureIndex = { starts: [], ids: [] }
  const shadow = { positions: [] as number[], alphas: [] as number[] }
  const positions: number[] = []
  const vertexColors: number[] = []
  const color = new THREE.Color()
  const matrix = new THREE.Matrix4()
  const v = new THREE.Vector3()
  const up = new THREE.Vector3(0, 1, 0)
  const tablesByRoom = new Map<string, PlanAsset[]>()
  for (const asset of assets) {
    if (TABLES.has(asset.type)) tablesByRoom.set(asset.space, [...(tablesByRoom.get(asset.space) ?? []), asset])
  }

  for (const asset of assets) {
    index.starts.push(positions.length / 3)
    index.ids.push(asset.id)
    const [X, Z] = place(asset.position[0], asset.position[1])
    const fit = placement(asset, rooms.get(asset.space), tablesByRoom.get(asset.space) ?? [])
    const width = Math.max(0.15, fit.width - 0.03)
    const depth = Math.max(0.15, fit.depth - 0.03)
    matrix.compose(new THREE.Vector3(X, 0, Z), new THREE.Quaternion().setFromAxisAngle(up, fit.angle), new THREE.Vector3(width, 1, depth))
    if (!OFF_FLOOR.has(asset.type)) contactShadow(shadow, X, Z, fit.angle, width, depth)
    for (const part of model(asset)) {
      color.set(colors[part.m])
      const corners = part.shape === 'box' ? boxTriangles(part) : prismTriangles(part)
      for (const [x, y, z] of corners) {
        v.set(x, y, z).applyMatrix4(matrix)
        positions.push(v.x, v.y, v.z)
        vertexColors.push(color.r, color.g, color.b)
      }
    }
  }
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
  geometry.setAttribute('color', new THREE.Float32BufferAttribute(vertexColors, 3))
  geometry.computeVertexNormals()
  geometry.userData.baseColors = Float32Array.from(vertexColors)
  index.starts.push(positions.length / 3)
  const contact = new THREE.BufferGeometry()
  contact.setAttribute('position', new THREE.Float32BufferAttribute(shadow.positions, 3))
  contact.setAttribute('alpha', new THREE.Float32BufferAttribute(shadow.alphas, 1))
  return { geometry, index, contact }
}

/** A soft shadow under a piece: dark over its footprint, fading out CONTACT_SPREAD_M beyond it. */
function contactShadow(out: { positions: number[]; alphas: number[] }, X: number, Z: number, angle: number, width: number, depth: number) {
  const c = Math.cos(angle)
  const s = Math.sin(angle)
  // local (x, z) → scene, matching the model's rotation about +Y
  const at = (x: number, z: number): [number, number] => [X + x * c + z * s, Z - x * s + z * c]
  const inner = [[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([i, j]) => at((i * width) / 2 * 0.9, (j * depth) / 2 * 0.9))
  const outer = [[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([i, j]) => at(i * (width / 2 + CONTACT_SPREAD_M), j * (depth / 2 + CONTACT_SPREAD_M)))
  const y = 0.005
  const push = (p: [number, number], alpha: number) => {
    out.positions.push(p[0], y, p[1])
    out.alphas.push(alpha)
  }
  push(inner[0], 0.85); push(inner[1], 0.85); push(inner[2], 0.85)
  push(inner[0], 0.85); push(inner[2], 0.85); push(inner[3], 0.85)
  for (let k = 0; k < 4; k++) {
    const a = inner[k]
    const b = inner[(k + 1) % 4]
    const B = outer[(k + 1) % 4]
    const A = outer[k]
    push(a, 0.85); push(b, 0.85); push(B, 0)
    push(a, 0.85); push(B, 0); push(A, 0)
  }
}

/** Asset id owning a vertex (binary search over the ranges). */
export function assetAt(index: FurnitureIndex, vertex: number): string | null {
  let lo = 0
  let hi = index.ids.length - 1
  while (lo <= hi) {
    const mid = (lo + hi) >> 1
    if (vertex < index.starts[mid]) hi = mid - 1
    else if (vertex >= index.starts[mid + 1]) lo = mid + 1
    else return index.ids[mid]
  }
  return null
}

/** Tint one piece (or restore its own colours with hex = null). */
export function paintAsset(geometry: THREE.BufferGeometry, index: FurnitureIndex, id: string, hex: string | null) {
  const k = index.ids.indexOf(id)
  if (k < 0) return
  const attribute = geometry.getAttribute('color') as THREE.BufferAttribute
  const base = geometry.userData.baseColors as Float32Array
  const color = new THREE.Color(hex ?? '#000')
  for (let i = index.starts[k]; i < index.starts[k + 1]; i++) {
    if (hex) attribute.setXYZ(i, color.r, color.g, color.b)
    else attribute.setXYZ(i, base[i * 3], base[i * 3 + 1], base[i * 3 + 2])
  }
  attribute.needsUpdate = true
}

type P = [number, number, number]

function quad(out: P[], a: P, b: P, c: P, d: P) {
  out.push(a, b, c, a, c, d)
}

function boxTriangles({ x, y, z }: Part): P[] {
  const [x0, x1] = x
  const [y0, y1] = y
  const [z0, z1] = z
  const out: P[] = []
  quad(out, [x0, y1, z0], [x0, y1, z1], [x1, y1, z1], [x1, y1, z0]) // top
  quad(out, [x0, y0, z0], [x1, y0, z0], [x1, y0, z1], [x0, y0, z1]) // bottom
  quad(out, [x0, y0, z0], [x0, y1, z0], [x1, y1, z0], [x1, y0, z0]) // -z
  quad(out, [x1, y0, z1], [x1, y1, z1], [x0, y1, z1], [x0, y0, z1]) // +z
  quad(out, [x0, y0, z1], [x0, y1, z1], [x0, y1, z0], [x0, y0, z0]) // -x
  quad(out, [x1, y0, z0], [x1, y1, z0], [x1, y1, z1], [x1, y0, z1]) // +x
  return out
}

function prismTriangles({ x, y, z }: Part): P[] {
  const cx = (x[0] + x[1]) / 2
  const cz = (z[0] + z[1]) / 2
  const rx = (x[1] - x[0]) / 2
  const rz = (z[1] - z[0]) / 2
  const ring = Array.from({ length: SIDES }, (_, i) => {
    const t = ((i + 0.5) / SIDES) * Math.PI * 2
    return [cx + Math.cos(t) * rx, cz + Math.sin(t) * rz] as const
  })
  const out: P[] = []
  for (let i = 0; i < SIDES; i++) {
    const [ax, az] = ring[i]
    const [bx, bz] = ring[(i + 1) % SIDES]
    quad(out, [ax, y[0], az], [ax, y[1], az], [bx, y[1], bz], [bx, y[0], bz])
    out.push([cx, y[1], cz], [bx, y[1], bz], [ax, y[1], az])
    out.push([cx, y[0], cz], [ax, y[0], az], [bx, y[0], bz])
  }
  return out
}
