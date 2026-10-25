// The landing map stays mounted under the building screen; this is how the two talk. The building's model keeps
// its own camera (src/plan/PlanView.tsx) and the map follows it, so the city sits around the model: the kit's
// metres run x east and y north from the building's `origin` (backend/locations.json), the same frame as the map.
// The model's camera is orthographic and the map's perspective, so the map flattens its perspective while it follows
// (a 1° field of view; narrower drops tiles when tilted): then both agree to a few pixels across the screen.

import type { ExpressionSpecification, GeoJSONSource, Map as MapLibreMap, MapSourceDataEvent } from 'maplibre-gl'
import { neighbourLayer, type Neighbour } from './neighbours'
import { blockLook, BUILDINGS_3D_FILTER, rgb } from './style'

const R = 6378137 // the sphere the (archived) georef.py projected the OSM outline with
const TILE_PX = 512 // MapLibre's world is 512 px wide at zoom 0

/** The steepest tilt the model takes while the map follows it: past 60° MapLibre switches to another tile selection
 * and, with the narrow field of view used here, draws no buildings at street zooms (measured at z15–18). */
export const MAX_MAP_PITCH = 60
/** The map's field of view while it follows the model: ≤ ~10 px apart from the orthographic model at the screen
 * edges (4° was up to 40 px); narrower, MapLibre drops tiles when tilted. */
export const FLAT_FOV = 1

export type Origin = { lat: number; lon: number }
/** A camera in the building's metres: the ground point at the centre of the screen, pixels per metre, the tilt
 * from straight down and the turn from north (degrees, clockwise), as MapLibre takes them. */
export type View = { x: number; y: number; scale: number; pitch: number; bearing: number }

let map: MapLibreMap | null = null

const rad = (deg: number) => (deg * Math.PI) / 180
const deg = (r: number) => (r * 180) / Math.PI

// the open building: its footprint (lng/lat for the tiles, metres for the x-ray), its height, and its own extruded
// OSM blocks (its outline, or the parts it is split into), which the model replaces
let blocks: { id: string; origin: Origin; rings: [number, number][][]; metres: [number, number][][]; height: number } | null = null

/** One of the open building's OSM blocks in the building's metres (outer rings), from its base to its top. */
export type ShellBlock = { rings: [number, number][][]; base: number; top: number }
let shell: ShellBlock[] = []
const shellListeners = new Set<(blocks: ShellBlock[]) => void>()
/** The open building's OSM blocks, now and whenever they change (the model draws them as a wireframe). */
export function onShell(listener: (blocks: ShellBlock[]) => void) {
  shellListeners.add(listener)
  listener(shell)
  return () => void shellListeners.delete(listener)
}

let ownIds: number[] = [] // blocks left out: the open building's own, those under a building with a model, and those around it
let filtersKey = '' // what the filters were last set from (setting one makes the map re-process its tiles)
let dirty = true // tiles or the models changed since the blocks were last gathered
let restKey = '' // what the put-back pieces were last built from, and into which source
let restSource: GeoJSONSource | undefined
let dark = false // the map's theme, for the colours of the blocks drawn around the open building
let around = 0 // how many blocks the x-ray layer draws (dev checks)
const NEAR_M = 500 // the blocks this close to the open building's middle are drawn with the x-ray (./neighbours.ts)
const XRAY_LAYER = 'buildings-xray'
const xray = neighbourLayer(XRAY_LAYER, () => blockLook(dark))

const onData = (event: MapSourceDataEvent) => {
  if (event.sourceId === 'openmaptiles' || event.sourceId === 'models') dirty = true
}
// tiles arrive over time: gather the blocks again once the map is idle, if any arrived (not on every idle: a pan
// that loads nothing new should cost nothing)
const onIdle = () => dirty && applyBlocks()

export const attachMap = (next: MapLibreMap | null) => {
  map?.off('idle', onIdle)
  map?.off('sourcedata', onData)
  map = next
  map?.on('idle', onIdle)
  map?.on('sourcedata', onData)
  dirty = true
  if (import.meta.env.DEV) Object.assign(window, { __bridge: { state: () => ({ blocks, shell, around, ownIds, restKey, dirty }), applyBlocks } }) // checks
}

/** How tall the map's own blocks are where each building stands (OSM `render_height`, the tallest block that
 * overlaps its footprint), so its accent block can wrap them; null where no block is loaded yet. In the tiles a
 * building is often one wing of a bigger block (the TUM main building is one polygon), so overlap is tested
 * three ways: the block's centre in the footprint, the footprint's centre in the block, or most of the block's
 * corners in the footprint (a U-shaped building has its centre in the courtyard). */
export function osmHeights(footprints: [number, number][][][]): (number | null)[] {
  const tallest: (number | null)[] = footprints.map(() => null)
  if (!map?.getSource('openmaptiles')) return tallest
  const centres = footprints.map((rings) => rings.map((ring) => centreOf({ type: 'Polygon', coordinates: [ring] })))
  const boxes = footprints.map((rings) => (rings.length ? boxOf(rings.flat()) : null))
  for (const feature of map.querySourceFeatures('openmaptiles', { sourceLayer: 'building' })) {
    const height = Number(feature.properties?.render_height)
    if (!Number.isFinite(height)) continue
    // each polygon of a merged feature on its own (see applyBlocks), its box first
    for (const ring of outerRings(feature.geometry) as [number, number][][]) {
      const box = boxOf(ring)
      let centre: number[] | null | undefined
      footprints.forEach((rings, i) => {
        const own = boxes[i]
        if (!own || !meet(box, own)) return
        centre ??= centreOf({ type: 'Polygon', coordinates: [ring] })
        if (centre && overlaps(ring, centre, rings, centres[i])) tallest[i] = Math.max(tallest[i] ?? 0, height)
      })
    }
  }
  return tallest
}

/** A tile block over a footprint (rings, their centres): its centre in the footprint, the footprint's centre in it, or
 * most of its corners in the footprint. */
function overlaps(ring: number[][], centre: number[], rings: [number, number][][], centres: (number[] | null)[]) {
  return (
    rings.some((own) => inside(centre, own)) ||
    centres.some((own) => own && inside(own, ring as [number, number][])) ||
    ring.filter((corner) => rings.some((own) => inside(corner, own))).length >= ring.length / 2
  )
}

type Box = [number, number, number, number]
const boxOf = (points: number[][]): Box =>
  points.reduce<Box>(([x0, y0, x1, y1], [x, y]) => [Math.min(x0, x), Math.min(y0, y), Math.max(x1, x), Math.max(y1, y)], [Infinity, Infinity, -Infinity, -Infinity])
const meet = (a: Box, b: Box) => a[0] <= b[2] && b[0] <= a[2] && a[1] <= b[3] && b[1] <= a[3]

const SHARE_SAMPLES = 24 // per side of the sampling grid
/** Whether a tile block and a footprint mostly coincide: of the smaller of the two, at least half lies inside the
 * other (sampled on a grid over where their boxes meet). Catches what the point tests miss: a U-shaped block whose
 * centre is in its courtyard and whose corners sit on the footprint's edge (the tiles round them). */
function shared(ring: [number, number][], rings: [number, number][][]) {
  const box = (points: [number, number][]) => points.reduce(([x0, y0, x1, y1], [x, y]) => [Math.min(x0, x), Math.min(y0, y), Math.max(x1, x), Math.max(y1, y)], [Infinity, Infinity, -Infinity, -Infinity])
  const [ax0, ay0, ax1, ay1] = box(ring)
  const [bx0, by0, bx1, by1] = box(rings.flat())
  const [x0, y0, x1, y1] = [Math.max(ax0, bx0), Math.max(ay0, by0), Math.min(ax1, bx1), Math.min(ay1, by1)]
  if (x0 >= x1 || y0 >= y1) return false
  const inFootprint = (point: number[]) => rings.some((own) => inside(point, own))
  // areas by sampling each shape's own box, the overlap over the shared box
  const area = (test: (point: number[]) => boolean, [sx0, sy0, sx1, sy1]: number[]) => {
    let hits = 0
    for (let i = 0; i < SHARE_SAMPLES; i++)
      for (let j = 0; j < SHARE_SAMPLES; j++)
        if (test([sx0 + ((i + 0.5) / SHARE_SAMPLES) * (sx1 - sx0), sy0 + ((j + 0.5) / SHARE_SAMPLES) * (sy1 - sy0)])) hits++
    return (hits / SHARE_SAMPLES ** 2) * (sx1 - sx0) * (sy1 - sy0)
  }
  const both = area((point) => inside(point, ring) && inFootprint(point), [x0, y0, x1, y1])
  if (!both) return false
  const smaller = Math.min(area((point) => inside(point, ring), [ax0, ay0, ax1, ay1]), area(inFootprint, [bx0, by0, bx1, by1]))
  return both >= smaller / 2
}

type Geometry = ReturnType<MapLibreMap['querySourceFeatures']>[number]['geometry'] | { type: 'Polygon'; coordinates: number[][][] }
const outerRing = (geometry: Geometry) =>
  geometry.type === 'Polygon' ? geometry.coordinates[0] : geometry.type === 'MultiPolygon' ? geometry.coordinates[0]?.[0] : null

/** every polygon of a polygon or multipolygon, with its holes */
const polygonsOf = (geometry: Geometry): number[][][][] =>
  geometry.type === 'Polygon' ? [geometry.coordinates] : geometry.type === 'MultiPolygon' ? (geometry.coordinates as number[][][][]) : []

/** every outer ring of a polygon or multipolygon */
const outerRings = (geometry: Geometry): number[][][] =>
  geometry.type === 'Polygon' ? geometry.coordinates.slice(0, 1) : geometry.type === 'MultiPolygon' ? geometry.coordinates.map((polygon: number[][][]) => polygon[0]) : []

/** a shape's centre: the mean of its outer ring (tiles clip blocks, close enough to tell whose footprint it is in) */
function centreOf(geometry: Geometry): number[] | null {
  const ring = outerRing(geometry)
  if (!ring?.length) return null
  const centre = [0, 0]
  for (const [x, y] of ring) {
    centre[0] += x / ring.length
    centre[1] += y / ring.length
  }
  return centre
}

export const toLngLat = (origin: Origin, x: number, y: number): [number, number] => [
  origin.lon + deg(x / (R * Math.cos(rad(origin.lat)))),
  origin.lat + deg(y / R),
]

/** the inverse of toLngLat: a map point in the building's metres */
export const fromLngLat = (origin: Origin, lng: number, lat: number): [number, number] => [
  rad(lng - origin.lon) * R * Math.cos(rad(origin.lat)),
  rad(lat - origin.lat) * R,
]

const metresPerWorld = (lat: number) => 2 * Math.PI * R * Math.cos(rad(lat))
export const zoomFor = (scale: number, lat: number) => Math.log2((scale * metresPerWorld(lat)) / TILE_PX)

/** Move the map to the model's camera (no animation: it is called on every frame the model draws). */
export function follow(origin: Origin, view: View) {
  if (!map) return
  if (map.getVerticalFieldOfView() !== FLAT_FOV) map.setVerticalFieldOfView(FLAT_FOV) // whatever happened before
  map.jumpTo({ center: toLngLat(origin, view.x, view.y), zoom: zoomFor(view.scale, origin.lat), pitch: view.pitch, bearing: view.bearing })
}

/** The map's camera now, in the building's metres: where the model's camera starts so it takes over seamlessly. */
export function mapView(origin: Origin): View | null {
  if (!map) return null
  const centre = map.getCenter()
  return {
    x: rad(centre.lng - origin.lon) * R * Math.cos(rad(origin.lat)),
    y: rad(centre.lat - origin.lat) * R,
    scale: (TILE_PX * 2 ** map.getZoom()) / metresPerWorld(centre.lat),
    pitch: map.getPitch(),
    bearing: map.getBearing(),
  }
}

/** Resolves once the map has stopped moving (the fly-in to a building), at once if there is no map. */
export function settled(): Promise<void> {
  const current = map
  if (!current || !current.isMoving()) return Promise.resolve()
  // not the first moveend: easing the field of view fires one on every step while the flight goes on
  return new Promise((resolve) => {
    const check = () => {
      if (current.isMoving()) return
      current.off('moveend', check)
      resolve()
    }
    current.on('moveend', check)
  })
}

/** The building pin under a screen point (client px), if any: a tap on the city around the model opens it. */
export function pinAt(x: number, y: number): string | null {
  if (!map || !map.getLayer('pins')) return null
  const box = map.getContainer().getBoundingClientRect()
  const [px, py] = [x - box.left, y - box.top]
  const slop = 12
  const [hit] = map.queryRenderedFeatures([[px - slop, py - slop], [px + slop, py + slop]], { layers: ['pins', 'pin-names'] })
  const id = hit?.properties?.id
  return typeof id === 'string' ? id : null
}

/** Hide the map's 3D blocks that stand inside the building's outline (rings in the building's metres, any floor);
 * `height` is how tall the model stands above the ground (metres), for the x-ray. */
export function hideBlocks(id: string, origin: Origin, rings: [number, number][][], height: number) {
  blocks = { id, origin, rings: rings.map((ring) => ring.map(([x, y]) => toLngLat(origin, x, y))), metres: rings, height }
  applyBlocks()
}

/** The map's theme: the blocks drawn around the open building take its colours. */
export function setTheme(next: boolean) {
  if (next === dark) return
  dark = next
  dirty = true
}

/** Bring them back when that building's screen has gone. */
export function showBlocks(id: string) {
  if (blocks?.id !== id) return
  blocks = null
  applyBlocks()
}

/** (Re)apply the map's blocks: after tiles load and after a style swap. Three kinds of tile block leave the solid layer:
 * - those under a building with a model, which MapLanding draws in the accent as tall as them: two blocks on the
 *   same outline z-fight (flicker), worst with the narrow field of view used over a model;
 * - with a building open, those over its footprint: the model draws them as a wireframe instead (onShell), so it
 *   is not boxed in by the map's own volume of it (a campus wing is often one block with its neighbours);
 * - with a building open, those around it (NEAR_M): drawn by the x-ray layer instead (./neighbours.ts), which cuts
 *   away what stands in front of the building, and the buildings with a model around it with them.
 * Matched by overlap, since the tiles' building ids are not the kit's way ids. */
export function applyBlocks() {
  if (!map?.getLayer('buildings-3d')) return
  dirty = false
  const ids = new Set<number>()
  const own = new Map<number, ShellBlock & { size: number }>()
  const origin = blocks?.origin
  const ownCentres = blocks ? blocks.rings.map((ring) => centreOf({ type: 'Polygon', coordinates: [ring] })) : []
  const look = blockLook(dark)
  const neighbours: Neighbour[] = []
  const nearby = (lng: number, lat: number) => !!origin && Math.hypot(...fromLngLat(origin, lng, lat)) <= NEAR_M
  // the buildings with a model, drawn in the accent over their OSM blocks (src/map/MapLanding.tsx)
  const models: { id: string; ring: [number, number][]; centre: number[] | null }[] = []
  const nearModels = new Set<string>()
  if (map.getSource('models'))
    for (const feature of map.querySourceFeatures('models')) {
      const id = feature.properties?.id
      if (typeof id !== 'string') continue
      // as tall as MapLanding draws it: the kit or the OSM block, whichever is taller, and a little more
      const top = Math.max(Number(feature.properties?.height ?? 0), Number(feature.properties?.osm ?? 0)) + 0.4
      for (const polygon of polygonsOf(feature.geometry)) {
        const ring = polygon[0] as [number, number][]
        const centre = centreOf({ type: 'Polygon', coordinates: [ring] })
        models.push({ id, ring, centre })
        if (blocks && id !== blocks.id && centre && nearby(centre[0], centre[1]) && !nearModels.has(`${id}#${ring.length}#${ring[0]}`)) {
          nearModels.add(`${id}#${ring.length}#${ring[0]}`)
          neighbours.push({ rings: polygon as [number, number][][], base: 0, top, colour: shade(look.ours, look.oursRoof, top) })
        }
      }
    }
  const modelRings = models.map((model) => model.ring)
  const modelCentres = models.map((model) => model.centre)
  // boxes first: the overlap tests are only run on a polygon whose box meets the footprint's
  const ownBox = blocks ? boxOf(blocks.rings.flat()) : null
  const modelBoxes = models.map((model) => boxOf(model.ring))
  // tested only against the footprints whose box meets the polygon's (the area test samples every one it is given)
  const coveredByModel = (ring: [number, number][], centre: number[], box: Box) => {
    const close = models.flatMap((_, i) => (meet(box, modelBoxes[i]) ? [i] : []))
    if (!close.length) return false
    const rings = close.map((i) => modelRings[i])
    return overlaps(ring, centre, rings, close.map((i) => modelCentres[i])) || shared(ring, rings)
  }
  // a feature can be several blocks the tiles merged (same height and look), often hundreds across the city: each
  // polygon is tested on its own; a filter can only hide the feature whole, so when any of its polygons has to go
  // the feature is left out and its other polygons are put back (./style.ts `buildings-3d-rest`)
  const rest: { type: 'Feature'; properties: Record<string, number>; geometry: { type: 'Polygon'; coordinates: number[][][] } }[] = []
  for (const feature of map.querySourceFeatures('openmaptiles', { sourceLayer: 'building' })) {
    if (feature.id === undefined || feature.properties?.hide_3d === true) continue
    const id = Number(feature.id)
    const base = Number(feature.properties?.render_min_height ?? 0)
    const top = Number(feature.properties?.render_height ?? 6)
    const mine: [number, number][][] = []
    const kept: number[][][][] = []
    let taken = false
    for (const polygon of polygonsOf(feature.geometry)) {
      const ring = polygon[0] as [number, number][]
      const centre = centreOf({ type: 'Polygon', coordinates: [ring] })
      if (!centre) continue
      const box = boxOf(ring)
      if (blocks && origin && ownBox && meet(box, ownBox) && (overlaps(ring, centre, blocks.rings, ownCentres) || shared(ring, blocks.rings))) mine.push(ring.map(([lng, lat]) => fromLngLat(origin, lng, lat)))
      else if (coveredByModel(ring, centre, box)) taken = true
      else if (nearby(centre[0], centre[1])) {
        taken = true
        neighbours.push({ rings: polygon as [number, number][][], base, top, colour: shade(look.wall, look.roof, feature.properties?.render_height ?? 6) })
      } else kept.push(polygon)
    }
    const leftOut = taken || mine.length > 0
    if (!leftOut) continue
    ids.add(id)
    for (const polygon of kept) rest.push({ type: 'Feature', properties: { piece: rest.length, render_height: top, render_min_height: base }, geometry: { type: 'Polygon', coordinates: polygon } })
    if (!mine.length) continue
    // a block crossing a tile edge comes once per tile, clipped: keep its biggest piece
    const size = mine.reduce((sum, ring) => sum + ring.length, 0)
    if ((own.get(id)?.size ?? -1) < size) own.set(id, { rings: mine, base, top, size })
  }
  // rebuilt only when what it is built from changed (tiles arrive, a building opens or closes)
  const key = `${[...ids].join(',')}|${rest.length}`
  const source = map.getSource('rest') as GeoJSONSource | undefined
  if (source && (key !== restKey || source !== restSource)) {
    restKey = key
    restSource = source // a theme change swaps the style, and with it an empty source
    source.setData({ type: 'FeatureCollection', features: rest })
  }
  shell = [...own.values()].map(({ rings, base, top }) => ({ rings, base, top }))
  shellListeners.forEach((listener) => listener(shell))
  ownIds = [...ids]
  around = neighbours.length
  // the x-ray layer: in the map while a building is open, under the pins (they stay on top of every block)
  if (blocks && origin) {
    if (!map.getLayer(XRAY_LAYER)) map.addLayer(xray, map.getLayer('pin-discs') ? 'pin-discs' : undefined)
    xray.setBlocks({ origin, rings: blocks.metres, height: blocks.height }, neighbours)
  } else if (map.getLayer(XRAY_LAYER)) map.removeLayer(XRAY_LAYER)
  applyFilters([...nearModels].map((key) => key.split('#')[0]))
}

/** Set the filters, only when what they are built from changed (setting one makes the map re-process its tiles). */
function applyFilters(nearModels: string[]) {
  if (!map?.getLayer('buildings-3d')) return
  const hidden = [...new Set([...nearModels, ...(blocks ? [blocks.id] : [])])]
  const key = `${restKey}|${ownIds.join(',')}|${hidden.join(',')}`
  if (key === filtersKey) return
  filtersKey = key
  map.setFilter('buildings-3d', ['all', BUILDINGS_3D_FILTER as ExpressionSpecification, ['!', ['in', ['id'], ['literal', ownIds]]]])
  if (map.getLayer('model-blocks')) map.setFilter('model-blocks', hidden.length ? ['!', ['in', ['get', 'id'], ['literal', hidden]]] : null)
}

/** A block's colour as the map draws it: wall colour at the ground to roof colour at 45 m (./style.ts). */
const shade = (wall: string, roof: string, height: number): [number, number, number] => {
  const t = Math.min(1, Math.max(0, height / 45))
  const [a, b] = [rgb(wall), rgb(roof)]
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t]
}

function inside([px, py]: number[], ring: [number, number][]) {
  let hit = false
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i]
    const [xj, yj] = ring[j]
    if (yi > py !== yj > py && px < ((xj - xi) * (py - yi)) / (yj - yi) + xi) hit = !hit
  }
  return hit
}
