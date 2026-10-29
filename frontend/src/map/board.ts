// The compact island board of an organisation's map (docs/product/organizations.md, phase 3). The map does not show
// the world: the map's buildings are grouped into sites (buildings within NEARBY_M of each other, like the Guide's
// campus, backend/agents/campus.py), each site is an island (the rectangle round its buildings plus MARGIN_M), and
// the islands sit edge to edge in a row (a column on a phone) instead of kilometres apart. An island is only moved,
// never turned or scaled: inside it streets, blocks and buildings keep their true size and north, and the seam between
// two islands says how far apart they really are.
// The move is a translation in Web Mercator "world" units (0..1 across the map, y down), in whole steps of the z14
// tiles' 4096 grid (STEP), so the base map's tiles can be cut and moved exactly (./boardTiles.ts) and the buildings,
// their pins and the open model move by the same amount. (A move north or south changes Mercator's scale a little:
// about 0.3 % per 15 km at Munich's latitude, a third of a metre across a 100 m building.)
// Pure: `node --experimental-strip-types frontend/scripts/board.check.ts` checks it.

export type LngLat = [number, number]
/** in world units, y down */
export type Rect = { x0: number; y0: number; x1: number; y1: number }
/** `real`: where the island's area is; `dx`, `dy`: its move onto the board */
export type Island = { buildings: string[]; real: Rect; dx: number; dy: number }
/** `at`: where the label goes, past the seam's end on the table (`anchor`: the label's side that touches it), so it
 * never covers a pin or a name */
export type Seam = { line: [LngLat, LngLat]; label: string; at: LngLat; anchor: 'top' | 'right' }
/** `key` changes whenever the islands or their places do (the board's tiles are fetched under it) */
export type Board = { key: string; islands: Island[]; seams: Seam[] }
export type Arrangement = 'row' | 'column'
/** a building as the board needs it: its outline points (or its position alone) */
export type Site = { id: string; points: LngLat[] }

export const NEARBY_M = 600 // backend/agents/campus.py NEARBY_M: buildings this close are one site
export const MARGIN_M = 150 // the streets round a site's buildings that its island shows
export const STEP = 2 ** -26 // one unit of a z14 tile's 4096 grid (2^14 · 2^12 units across the world)
const R = 6378137

export const worldX = (lng: number) => (lng + 180) / 360
export const worldY = (lat: number) => {
  const s = Math.sin((lat * Math.PI) / 180)
  return 0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI)
}
export const lngOf = (x: number) => x * 360 - 180
export const latOf = (y: number) => (360 / Math.PI) * Math.atan(Math.exp((0.5 - y) * 2 * Math.PI)) - 90
/** metres in one world unit at a latitude */
const metresPerUnit = (lat: number) => 2 * Math.PI * R * Math.cos((lat * Math.PI) / 180)
/** metres between two points (equirectangular: sites are at most a few hundred km apart) */
export function metresBetween([lng1, lat1]: LngLat, [lng2, lat2]: LngLat) {
  const k = Math.PI / 180
  const east = (lng2 - lng1) * k * R * Math.cos(((lat1 + lat2) / 2) * k)
  return Math.hypot(east, (lat2 - lat1) * k * R)
}

const centre = (rect: Rect): [number, number] => [(rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2]
const at = ([x, y]: [number, number]): LngLat => [lngOf(x), latOf(y)]
const outward = (value: number, up: boolean) => (up ? Math.ceil(value / STEP) : Math.floor(value / STEP)) * STEP

/** The sites: buildings whose positions lie within NEARBY_M of another in the site (single linkage). */
export function islandsOf(sites: Site[]): { buildings: string[]; real: Rect }[] {
  const placed = sites.filter((site) => site.points.length)
  const middle = placed.map((site): LngLat => [
    site.points.reduce((sum, [lng]) => sum + lng, 0) / site.points.length,
    site.points.reduce((sum, [, lat]) => sum + lat, 0) / site.points.length,
  ])
  const group = placed.map((_, i) => i)
  const root = (i: number): number => (group[i] === i ? i : (group[i] = root(group[i])))
  for (let a = 0; a < placed.length; a++)
    for (let b = a + 1; b < placed.length; b++) if (metresBetween(middle[a], middle[b]) <= NEARBY_M) group[root(a)] = root(b)
  const members = new Map<number, number[]>()
  placed.forEach((_, i) => members.set(root(i), [...(members.get(root(i)) ?? []), i]))
  return [...members.values()].map((indices) => {
    const points = indices.flatMap((i) => placed[i].points)
    const xs = points.map(([lng]) => worldX(lng))
    const ys = points.map(([, lat]) => worldY(lat))
    const lat = points.reduce((sum, [, value]) => sum + value, 0) / points.length
    const margin = MARGIN_M / metresPerUnit(lat)
    // snapped outward to the grid, so islands placed edge to edge meet without a hairline between them
    const real = {
      x0: outward(Math.min(...xs) - margin, false), y0: outward(Math.min(...ys) - margin, false),
      x1: outward(Math.max(...xs) + margin, true), y1: outward(Math.max(...ys) + margin, true),
    }
    return { buildings: indices.map((i) => placed[i].id), real }
  })
}

/** The distance a seam shows: metres to 10 m below 1 km, one decimal below 10 km, whole km beyond. */
export function distanceLabel(metres: number) {
  if (metres < 1000) return `${Math.round(metres / 10) * 10} m`
  if (metres < 10000) return `${(metres / 1000).toFixed(1)} km`
  return `${Math.round(metres / 1000)} km`
}

/** Islands in a row (west to east) or a column (north to south), each against the one before, centred on the first;
 * the first stays where it really is. */
export function arrange(islands: { buildings: string[]; real: Rect }[], arrangement: Arrangement): Board {
  const row = arrangement === 'row'
  const ordered = [...islands].sort((a, b) => (row ? centre(a.real)[0] - centre(b.real)[0] : centre(a.real)[1] - centre(b.real)[1]))
  const placed: Island[] = []
  const seams: Seam[] = []
  for (const island of ordered) {
    const before = placed[placed.length - 1]
    if (!before) {
      placed.push({ ...island, dx: 0, dy: 0 })
      continue
    }
    const first = centre(placed[0].real)
    const [cx, cy] = centre(island.real)
    const dx = row ? before.real.x1 + before.dx - island.real.x0 : Math.round((first[0] - cx) / STEP) * STEP
    const dy = row ? Math.round((first[1] - cy) / STEP) * STEP : before.real.y1 + before.dy - island.real.y0
    const next = { ...island, dx, dy }
    placed.push(next)
    const a = boardRect(before)
    const b = boardRect(next)
    const line: [LngLat, LngLat] = row
      ? [at([b.x0, Math.max(a.y0, b.y0)]), at([b.x0, Math.min(a.y1, b.y1)])]
      : [at([Math.max(a.x0, b.x0), b.y0]), at([Math.min(a.x1, b.x1), b.y0])]
    const apart = metresBetween(at(centre(before.real)), at(centre(island.real)))
    // (the map's Noto glyphs have no arrows: said in words)
    seams.push({ line, label: `${distanceLabel(apart)} apart`, at: row ? line[1] : line[0], anchor: row ? 'top' : 'right' })
  }
  const text = placed.map((island) => `${island.buildings.join(',')}@${island.dx / STEP},${island.dy / STEP}`).join('|')
  let hash = 5381
  for (let i = 0; i < text.length; i++) hash = ((hash * 33) ^ text.charCodeAt(i)) >>> 0
  return { key: `${arrangement[0]}${hash.toString(36)}`, islands: placed, seams }
}

/** where an island lies on the board */
export const boardRect = (island: Island): Rect => ({
  x0: island.real.x0 + island.dx, y0: island.real.y0 + island.dy, x1: island.real.x1 + island.dx, y1: island.real.y1 + island.dy,
})
/** a real point onto the board, moved with its island */
export const toBoard = (island: Island, [lng, lat]: LngLat): LngLat => [lngOf(worldX(lng) + island.dx), latOf(worldY(lat) + island.dy)]
/** a board point back to where it really is */
export const toReal = (island: Island, [lng, lat]: LngLat): LngLat => [lngOf(worldX(lng) - island.dx), latOf(worldY(lat) - island.dy)]
/** the island a board point lies on, if any */
export function islandAt(board: Board, [lng, lat]: LngLat): Island | null {
  const [x, y] = [worldX(lng), worldY(lat)]
  return board.islands.find((island) => {
    const rect = boardRect(island)
    return x >= rect.x0 && x <= rect.x1 && y >= rect.y0 && y <= rect.y1
  }) ?? null
}
/** the board's extent ([west, south], [east, north]), for framing and bounding the camera */
export function boardBounds(board: Board, pad = 0): [LngLat, LngLat] | null {
  if (!board.islands.length) return null
  const rects = board.islands.map(boardRect)
  const x0 = Math.min(...rects.map((r) => r.x0))
  const x1 = Math.max(...rects.map((r) => r.x1))
  const y0 = Math.min(...rects.map((r) => r.y0))
  const y1 = Math.max(...rects.map((r) => r.y1))
  const margin = Math.max(x1 - x0, y1 - y0) * pad
  return [at([x0 - margin, y1 + margin]), at([x1 + margin, y0 - margin])]
}

/** The board's islands (the ground the base map is cut to) and seams, as GeoJSON for ./style.ts boardStyle. */
export function boardShapes(board: Board) {
  const ring = (rect: Rect): LngLat[] => [at([rect.x0, rect.y0]), at([rect.x1, rect.y0]), at([rect.x1, rect.y1]), at([rect.x0, rect.y1]), at([rect.x0, rect.y0])]
  return {
    type: 'FeatureCollection' as const,
    features: [
      ...board.islands.map((island) => ({ type: 'Feature' as const, properties: { kind: 'island' }, geometry: { type: 'Polygon' as const, coordinates: [ring(boardRect(island))] } })),
      ...board.seams.map((seam) => ({ type: 'Feature' as const, properties: { kind: 'seam' }, geometry: { type: 'LineString' as const, coordinates: seam.line } })),
      ...board.seams.map((seam) => ({ type: 'Feature' as const, properties: { kind: 'seam-label', label: seam.label, anchor: seam.anchor }, geometry: { type: 'Point' as const, coordinates: seam.at } })),
    ],
  }
}

type Located = { id: string; location: { lat: number; lon: number; origin?: { lat: number; lon: number }; outline?: [number, number][][] } | null }

/** The board for a map's buildings (null when none has a position). */
export function boardOf(buildings: Located[], arrangement: Arrangement): Board | null {
  const sites = buildings.flatMap((b) => (b.location ? [{ id: b.id, points: b.location.outline?.flat().length ? b.location.outline.flat() : [[b.location.lon, b.location.lat] as LngLat] }] : []))
  return sites.length ? arrange(islandsOf(sites), arrangement) : null
}

/** A building as it stands on the board: position, origin and outline moved with its island (others as they are). */
export function onBoard<T extends Located>(board: Board, building: T): T {
  const island = board.islands.find((candidate) => candidate.buildings.includes(building.id))
  const location = building.location
  if (!island || !location || (!island.dx && !island.dy)) return building // the first island stays where it is
  const [lon, lat] = toBoard(island, [location.lon, location.lat])
  const origin = location.origin && toBoard(island, [location.origin.lon, location.origin.lat])
  return {
    ...building,
    location: {
      ...location, lat, lon,
      ...(origin ? { origin: { lat: origin[1], lon: origin[0] } } : {}),
      ...(location.outline ? { outline: location.outline.map((r) => r.map((point) => toBoard(island, point))) } : {}),
    },
  }
}
