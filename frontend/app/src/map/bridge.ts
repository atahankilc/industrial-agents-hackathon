// The landing map stays mounted under the building screen; this is how the two talk. The building's model keeps
// its own camera (src/plan/PlanView.tsx) and the map follows it, so the city sits around the model: the kit's
// metres run x east and y north from the building's `origin` (backend/locations.json), the same frame as the map.
// The model's camera is orthographic and the map's perspective, so the map flattens its perspective while it follows
// (a narrow field of view): then both agree to a few percent across a building.

import type { ExpressionSpecification, Map as MapLibreMap } from 'maplibre-gl'
import { BUILDINGS_3D_FILTER } from './style'

const R = 6378137 // the sphere the (archived) georef.py projected the OSM outline with
const TILE_PX = 512 // MapLibre's world is 512 px wide at zoom 0

export type Origin = { lat: number; lon: number }
/** A camera in the building's metres: the ground point at the centre of the screen, pixels per metre, the tilt
 * from straight down and the turn from north (degrees, clockwise), as MapLibre takes them. */
export type View = { x: number; y: number; scale: number; pitch: number; bearing: number }

let map: MapLibreMap | null = null

const rad = (deg: number) => (deg * Math.PI) / 180
const deg = (r: number) => (r * 180) / Math.PI

// the open building's own extruded OSM blocks (its outline, or the parts it is split into), which the model replaces
let blocks: { id: string; rings: [number, number][][] } | null = null

export const attachMap = (next: MapLibreMap | null) => {
  map?.off('idle', applyBlocks)
  map = next
  map?.on('idle', applyBlocks) // tiles arrive over time
}

/** How tall the map's own blocks are where each building stands (OSM `render_height`, the tallest block that
 * overlaps its footprint), so its accent block can wrap them; null where no block is loaded yet. In the tiles a
 * building is often one wing of a bigger block (the TUM main building is one polygon), so overlap is tested
 * both ways: the block's centre in the footprint, or the footprint's centre in the block. */
export function osmHeights(footprints: [number, number][][][]): (number | null)[] {
  const tallest: (number | null)[] = footprints.map(() => null)
  if (!map?.getSource('openmaptiles')) return tallest
  const centres = footprints.map((rings) => rings.map((ring) => centreOf({ type: 'Polygon', coordinates: [ring] })))
  for (const feature of map.querySourceFeatures('openmaptiles', { sourceLayer: 'building' })) {
    const height = Number(feature.properties?.render_height)
    const ring = outerRing(feature.geometry)
    const centre = centreOf(feature.geometry)
    if (!Number.isFinite(height) || !ring || !centre) continue
    footprints.forEach((rings, i) => {
      const overlaps = rings.some((own) => inside(centre, own)) || centres[i].some((own) => own && inside(own, ring as [number, number][]))
      if (overlaps) tallest[i] = Math.max(tallest[i] ?? 0, height)
    })
  }
  return tallest
}

type Geometry = ReturnType<MapLibreMap['querySourceFeatures']>[number]['geometry'] | { type: 'Polygon'; coordinates: number[][][] }
const outerRing = (geometry: Geometry) =>
  geometry.type === 'Polygon' ? geometry.coordinates[0] : geometry.type === 'MultiPolygon' ? geometry.coordinates[0]?.[0] : null

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

const metresPerWorld = (lat: number) => 2 * Math.PI * R * Math.cos(rad(lat))
export const zoomFor = (scale: number, lat: number) => Math.log2((scale * metresPerWorld(lat)) / TILE_PX)

/** Move the map to the model's camera (no animation: it is called on every frame the model draws). */
export function follow(origin: Origin, view: View) {
  if (!map) return
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

/** Hide the map's 3D blocks that stand inside the building's outline (rings in the building's metres, any floor). */
export function hideBlocks(id: string, origin: Origin, rings: [number, number][][]) {
  blocks = { id, rings: rings.map((ring) => ring.map(([x, y]) => toLngLat(origin, x, y))) }
  applyBlocks()
}

/** Bring them back when that building's screen has gone. */
export function showBlocks(id: string) {
  if (blocks?.id !== id) return
  blocks = null
  applyBlocks()
}

/** (Re)apply the hidden blocks: after tiles load and after a style swap. Blocks are matched by their centre, since
 * the tiles' building ids are not the kit's way ids (a building split into parts has several). */
export function applyBlocks() {
  if (!map?.getLayer('buildings-3d')) return
  if (!blocks) return void map.setFilter('buildings-3d', BUILDINGS_3D_FILTER)
  const ids = new Set<number>()
  for (const feature of map.querySourceFeatures('openmaptiles', { sourceLayer: 'building' })) {
    const centre = centreOf(feature.geometry)
    if (feature.id === undefined || !centre) continue
    if (blocks.rings.some((outline) => inside(centre, outline))) ids.add(Number(feature.id))
  }
  map.setFilter('buildings-3d', ['all', BUILDINGS_3D_FILTER as ExpressionSpecification, ['!', ['in', ['id'], ['literal', [...ids]]]]])
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
