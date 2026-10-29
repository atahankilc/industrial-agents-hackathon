// The base map's tiles for an island board (./board.ts): a `board://<key>/{z}/{x}/{y}` tile is cut together from the
// real OpenFreeMap tiles under each island it shows. Every feature of a real tile is clipped to the island's area and
// to the real tile's own square (its buffer would overlap the neighbouring tile's copy once both are moved), then
// moved by the island's offset in whole grid units and written into the board tile. The style, the OSM block
// heights and the blocks hidden under an open building (./bridge.ts) read it as the same `openmaptiles` source, with
// the same layers, properties and feature ids. Nothing is stored: the tiles are fetched live, so the board shows OSM
// as it is today. Known limit: a polygon cut at a real tile's edge draws that edge as a faint outline on layers that
// trace outlines (the flat `footprint` at z13–14.6).

import { VectorTile, type VectorTileLayer } from '@mapbox/vector-tile'
import { fromVectorTileJs, type VectorTileFeatureLike, type VectorTileLayerLike } from '@maplibre/vt-pbf'
import maplibregl from 'maplibre-gl'
import Pbf from 'pbf'
import { boardRect, type Board, type Rect } from './board'

export const TILEJSON = 'https://tiles.openfreemap.org/planet'
export const MAX_ZOOM = 14 // OpenMapTiles' deepest tiles; MapLibre overzooms the board beyond, as it does the real ones
const EXTENT = 4096
const KEEP_TILES = 256 // decoded real tiles kept for the next board tiles (each island needs the same few again)

type Point = { x: number; y: number }
type Feature = VectorTileFeatureLike

const boards = new Map<string, Board>()
let template: Promise<string> | null = null
const tiles = new Map<string, Promise<VectorTile | null>>()

/** Make a board's tiles available under `board://<key>/…` (the protocol is added once). */
export function registerBoard(board: Board) {
  if (!boards.size) maplibregl.addProtocol('board', boardTile)
  boards.set(board.key, board)
}
export const boardTilesUrl = (board: Board) => `board://${board.key}/{z}/{x}/{y}`

function realTile(z: number, x: number, y: number): Promise<VectorTile | null> {
  const id = `${z}/${x}/${y}`
  const cached = tiles.get(id)
  if (cached) {
    tiles.delete(id) // most recently used last
    tiles.set(id, cached)
    return cached
  }
  template ??= fetch(TILEJSON).then((response) => response.json()).then((json: { tiles: string[] }) => json.tiles[0])
  const loading = template
    .then((url) => fetch(url.replace('{z}', String(z)).replace('{x}', String(x)).replace('{y}', String(y))))
    .then((response) => (response.ok ? response.arrayBuffer() : null))
    .then((data) => (data ? new VectorTile(new Pbf(data)) : null))
  loading.catch(() => tiles.delete(id)) // a failed fetch is tried again next time
  tiles.set(id, loading)
  if (tiles.size > KEEP_TILES) tiles.delete(tiles.keys().next().value!)
  return loading
}

/** a ring (open: no closing point) cut to the rectangle, Sutherland–Hodgman side by side; possibly empty */
function clipRing(ring: Point[], box: Rect): Point[] {
  const sides: [(p: Point) => boolean, (a: Point, b: Point) => Point][] = [
    [(p) => p.x >= box.x0, (a, b) => ({ x: box.x0, y: a.y + ((b.y - a.y) * (box.x0 - a.x)) / (b.x - a.x) })],
    [(p) => p.x <= box.x1, (a, b) => ({ x: box.x1, y: a.y + ((b.y - a.y) * (box.x1 - a.x)) / (b.x - a.x) })],
    [(p) => p.y >= box.y0, (a, b) => ({ x: a.x + ((b.x - a.x) * (box.y0 - a.y)) / (b.y - a.y), y: box.y0 })],
    [(p) => p.y <= box.y1, (a, b) => ({ x: a.x + ((b.x - a.x) * (box.y1 - a.y)) / (b.y - a.y), y: box.y1 })],
  ]
  let out = ring
  for (const [inside, cross] of sides) {
    const input = out
    out = []
    for (let i = 0; i < input.length; i++) {
      const current = input[i]
      const previous = input[(i + input.length - 1) % input.length]
      if (inside(current)) {
        if (!inside(previous)) out.push(cross(previous, current))
        out.push(current)
      } else if (inside(previous)) out.push(cross(previous, current))
    }
    if (!out.length) return out
  }
  return out
}

/** a line cut to the rectangle: the pieces inside (Liang–Barsky per segment, joined where they meet) */
function clipLine(line: Point[], box: Rect): Point[][] {
  const pieces: Point[][] = []
  let piece: Point[] = []
  for (let i = 1; i < line.length; i++) {
    const a = line[i - 1]
    const b = line[i]
    let t0 = 0
    let t1 = 1
    const dx = b.x - a.x
    const dy = b.y - a.y
    let visible = true
    for (const [p, q] of [[-dx, a.x - box.x0], [dx, box.x1 - a.x], [-dy, a.y - box.y0], [dy, box.y1 - a.y]]) {
      if (p === 0) {
        if (q < 0) visible = false
      } else {
        const t = q / p
        if (p < 0) t0 = Math.max(t0, t)
        else t1 = Math.min(t1, t)
      }
    }
    if (!visible || t0 > t1) {
      if (piece.length > 1) pieces.push(piece)
      piece = []
      continue
    }
    const start = { x: a.x + t0 * dx, y: a.y + t0 * dy }
    const end = { x: a.x + t1 * dx, y: a.y + t1 * dy }
    if (!piece.length || t0 > 0) {
      if (piece.length > 1) pieces.push(piece)
      piece = [start]
    }
    piece.push(end)
    if (t1 < 1) {
      pieces.push(piece)
      piece = []
    }
  }
  if (piece.length > 1) pieces.push(piece)
  return pieces
}

/** One feature of a real tile clipped to `box` (its tile's units) and moved by (ox, oy); null when nothing is left. */
function moved(feature: { type: 0 | 1 | 2 | 3; id: number | undefined; properties: Record<string, number | string | boolean>; loadGeometry(): Point[][] }, scale: number, box: Rect, ox: number, oy: number): Feature | null {
  const geometry = feature.loadGeometry().map((ring) => ring.map((p) => ({ x: p.x * scale, y: p.y * scale })))
  let kept: Point[][]
  if (feature.type === 1) kept = geometry.map((points) => points.filter((p) => p.x >= box.x0 && p.x <= box.x1 && p.y >= box.y0 && p.y <= box.y1)).filter((points) => points.length)
  else if (feature.type === 2) kept = geometry.flatMap((line) => clipLine(line, box))
  else if (feature.type === 3) kept = geometry.map((ring) => clipRing(ring.slice(0, -1), box)) // rings come closed
  else kept = []
  const shifted = kept
    .map((ring) => ring.map((p) => ({ x: Math.round(p.x + ox), y: Math.round(p.y + oy) }))
      .filter((p, i, all) => feature.type === 1 || i === 0 || p.x !== all[i - 1].x || p.y !== all[i - 1].y))
    .filter((ring) => (feature.type === 3 ? ring.length >= 3 : feature.type === 2 ? ring.length >= 2 : ring.length >= 1))
    .map((ring) => (feature.type === 3 ? [...ring, ring[0]] : ring)) // the writer leaves the closing point out
  if (!shifted.length) return null
  return { type: feature.type, id: feature.id, properties: feature.properties, extent: EXTENT, loadGeometry: () => shifted as never }
}

/** the board tile z/x/y: every island over it, its real tiles cut and moved in */
async function boardTile(params: { url: string }): Promise<{ data: ArrayBuffer }> {
  const match = /^board:\/\/([^/]+)\/(\d+)\/(\d+)\/(\d+)/.exec(params.url)
  const board = match ? boards.get(match[1]) : undefined
  const layers = new Map<string, Feature[]>()
  if (match && board) {
    const [z, x, y] = [Number(match[2]), Number(match[3]), Number(match[4])]
    const n = 2 ** z
    const tile = { x0: x / n, y0: y / n, x1: (x + 1) / n, y1: (y + 1) / n }
    for (const island of board.islands) {
      const onBoard = boardRect(island)
      if (onBoard.x1 <= tile.x0 || onBoard.x0 >= tile.x1 || onBoard.y1 <= tile.y0 || onBoard.y0 >= tile.y1) continue
      // the real area this board tile shows of the island
      const area = {
        x0: Math.max(island.real.x0, tile.x0 - island.dx), y0: Math.max(island.real.y0, tile.y0 - island.dy),
        x1: Math.min(island.real.x1, tile.x1 - island.dx), y1: Math.min(island.real.y1, tile.y1 - island.dy),
      }
      // the island's offset in this zoom's grid units (whole units at z14; within half a unit, 1/16 px, below)
      const shiftX = Math.round(island.dx * n * EXTENT)
      const shiftY = Math.round(island.dy * n * EXTENT)
      const jobs: Promise<void>[] = []
      for (let tx = Math.floor(area.x0 * n); tx < Math.ceil(area.x1 * n); tx++)
        for (let ty = Math.floor(area.y0 * n); ty < Math.ceil(area.y1 * n); ty++)
          jobs.push(realTile(z, tx, ty).then((real) => {
            if (!real) return
            // the island's area in the real tile's units, never past the tile's own square
            const box = {
              x0: Math.max(0, (island.real.x0 * n - tx) * EXTENT), y0: Math.max(0, (island.real.y0 * n - ty) * EXTENT),
              x1: Math.min(EXTENT, (island.real.x1 * n - tx) * EXTENT), y1: Math.min(EXTENT, (island.real.y1 * n - ty) * EXTENT),
            }
            const ox = (tx - x) * EXTENT + shiftX
            const oy = (ty - y) * EXTENT + shiftY
            for (const [name, layer] of Object.entries(real.layers) as [string, VectorTileLayer][]) {
              const scale = EXTENT / layer.extent
              const out = layers.get(name) ?? []
              for (let i = 0; i < layer.length; i++) {
                const feature = moved(layer.feature(i), scale, box, ox, oy)
                if (feature) out.push(feature)
              }
              if (out.length) layers.set(name, out)
            }
          }))
      await Promise.all(jobs)
    }
  }
  const written: Record<string, VectorTileLayerLike> = {}
  for (const [name, features] of layers) written[name] = { version: 2, name, extent: EXTENT, length: features.length, feature: (i) => features[i] }
  const bytes = fromVectorTileJs({ layers: written })
  return { data: bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer }
}
