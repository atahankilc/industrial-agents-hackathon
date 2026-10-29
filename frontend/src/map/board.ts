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
// An org's editors may drag the islands elsewhere and name them: the map's `layout` (backend/api/routes/maps.py) keeps
// each site's name and move, and finds the site again by its buildings when the map changes. Once any island has been
// placed by hand, the board is the stored one on every screen; a site without a place goes to the right of it.
// Pure: `node --experimental-strip-types frontend/scripts/board.check.ts` checks it.

export type LngLat = [number, number]
/** in world units, y down */
export type Rect = { x0: number; y0: number; x1: number; y1: number }
/** `real`: where the island's area is; `dx`, `dy`: its move onto the board; `name`: given by the org's editors */
export type Island = { buildings: string[]; real: Rect; dx: number; dy: number; name: string | null }
/** an island before it is placed */
export type Piece = { buildings: string[]; real: Rect; name?: string | null }
/** one site of a map's stored layout: moves in STEP units, null = placed by the app */
export type SiteLayout = { buildings: string[]; name: string | null; dx: number | null; dy: number | null }
export type Layout = { sites?: SiteLayout[] }
/** `at`: where the label goes, past the seam's end on the table (`anchor`: the label's side that touches it), so it
 * never covers a pin or a name */
export type Seam = { line: [LngLat, LngLat]; label: string; at: LngLat; anchor: 'top' | 'right' }
/** `key` changes whenever the islands or their places do (the board's tiles are fetched under it); `byHand`: placed
 * by the map's layout, not lined up by the app */
export type Board = { key: string; islands: Island[]; seams: Seam[]; byHand: boolean }
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
export const at = ([x, y]: [number, number]): LngLat => [lngOf(x), latOf(y)]
const outward = (value: number, up: boolean) => (up ? Math.ceil(value / STEP) : Math.floor(value / STEP)) * STEP

/** The sites: buildings whose positions lie within NEARBY_M of another in the site (single linkage). */
export function islandsOf(sites: Site[]): Piece[] {
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
export function arrange(islands: Piece[], arrangement: Arrangement): Board {
  const row = arrangement === 'row'
  const ordered = [...islands].sort((a, b) => (row ? centre(a.real)[0] - centre(b.real)[0] : centre(a.real)[1] - centre(b.real)[1]))
  const placed: Island[] = []
  for (const island of ordered) {
    const before = placed[placed.length - 1]
    if (!before) {
      placed.push({ ...island, name: island.name ?? null, dx: 0, dy: 0 })
      continue
    }
    const first = centre(placed[0].real)
    const [cx, cy] = centre(island.real)
    const dx = row ? before.real.x1 + before.dx - island.real.x0 : Math.round((first[0] - cx) / STEP) * STEP
    const dy = row ? Math.round((first[1] - cy) / STEP) * STEP : before.real.y1 + before.dy - island.real.y0
    placed.push({ ...island, name: island.name ?? null, dx, dy })
  }
  return boardFrom(placed, arrangement[0])
}

/** A board from placed islands: a seam wherever two islands touch, a key from the places. */
function boardFrom(islands: Island[], prefix: string): Board {
  const text = islands.map((island) => `${island.buildings.join(',')}@${island.dx / STEP},${island.dy / STEP}`).join('|')
  let hash = 5381
  for (let i = 0; i < text.length; i++) hash = ((hash * 33) ^ text.charCodeAt(i)) >>> 0
  return { key: `${prefix}${hash.toString(36)}`, islands, seams: seamsOf(islands), byHand: prefix === 'l' }
}

/** The seams: wherever two islands meet along an edge (the label past the seam's lower or left end, on the table). */
export function seamsOf(islands: Island[]): Seam[] {
  const seams: Seam[] = []
  const meet = (a: number, b: number) => Math.abs(a - b) < STEP / 2
  for (let i = 0; i < islands.length; i++)
    for (let j = i + 1; j < islands.length; j++) {
      const a = boardRect(islands[i])
      const b = boardRect(islands[j])
      // (the map's Noto glyphs have no arrows: said in words)
      const label = `${distanceLabel(metresBetween(at(centre(islands[i].real)), at(centre(islands[j].real))))} apart`
      const top = Math.max(a.y0, b.y0)
      const bottom = Math.min(a.y1, b.y1)
      const left = Math.max(a.x0, b.x0)
      const right = Math.min(a.x1, b.x1)
      if ((meet(a.x1, b.x0) || meet(b.x1, a.x0)) && bottom - top > STEP) {
        const x = meet(a.x1, b.x0) ? b.x0 : a.x0
        const line: [LngLat, LngLat] = [at([x, top]), at([x, bottom])]
        seams.push({ line, label, at: line[1], anchor: 'top' })
      } else if ((meet(a.y1, b.y0) || meet(b.y1, a.y0)) && right - left > STEP) {
        const y = meet(a.y1, b.y0) ? b.y0 : a.y0
        const line: [LngLat, LngLat] = [at([left, y]), at([right, y])]
        seams.push({ line, label, at: line[0], anchor: 'right' })
      }
    }
  return seams
}

/** A stored layout's site for each island: the one sharing most buildings with it (each site taken once). */
function matchSites(islands: Piece[], sites: SiteLayout[]): (SiteLayout | null)[] {
  const taken = new Set<number>()
  return islands.map((island) => {
    let best = -1
    let shared = 0
    sites.forEach((site, i) => {
      const count = taken.has(i) ? 0 : site.buildings.filter((id) => island.buildings.includes(id)).length
      if (count > shared) [best, shared] = [i, count]
    })
    if (best < 0) return null
    taken.add(best)
    return sites[best]
  })
}

/** The islands where the layout put them; the ones it has no place for to the right, tops in line, edge to edge. */
function placeByLayout(islands: Piece[], sites: (SiteLayout | null)[]): Board {
  const placed: Island[] = []
  const loose: Piece[] = []
  islands.forEach((island, i) => {
    const site = sites[i]
    if (site && site.dx !== null && site.dy !== null) placed.push({ ...island, name: site.name, dx: site.dx * STEP, dy: site.dy * STEP })
    else loose.push({ ...island, name: site?.name ?? island.name ?? null })
  })
  const rects = placed.map(boardRect)
  let right = Math.max(...rects.map((rect) => rect.x1))
  const top = Math.min(...rects.map((rect) => rect.y0))
  for (const island of loose.sort((a, b) => centre(a.real)[0] - centre(b.real)[0])) {
    placed.push({ ...island, name: island.name ?? null, dx: right - island.real.x0, dy: top - island.real.y0 })
    right += island.real.x1 - island.real.x0
  }
  return boardFrom(placed, 'l')
}

/** The layout to store for a board: every island's buildings, name and move. */
export const layoutOf = (board: Board): Layout => ({
  sites: board.islands.map((island) => ({ buildings: island.buildings, name: island.name, dx: Math.round(island.dx / STEP), dy: Math.round(island.dy / STEP) })),
})

/** The board with one island moved to `rect` (its new place on the board, on the grid) or renamed. */
export function changed(board: Board, index: number, change: { rect?: Rect; name?: string | null }): Board {
  const islands = board.islands.map((island, i) => {
    if (i !== index) return island
    const rect = change.rect
    return {
      ...island,
      ...(rect ? { dx: Math.round((rect.x0 - island.real.x0) / STEP) * STEP, dy: Math.round((rect.y0 - island.real.y0) / STEP) * STEP } : {}),
      ...(change.name !== undefined ? { name: change.name?.trim() || null } : {}),
    }
  })
  return boardFrom(islands, 'l')
}

/** Island `index` dragged to `rect`: its edges pulled onto another island's within `pull` (world units), so islands
 * meet without a gap; null when it would then lie over another island. */
export function dropAt(board: Board, index: number, rect: Rect, pull: number): Rect | null {
  const others = board.islands.filter((_, i) => i !== index).map(boardRect)
  const width = rect.x1 - rect.x0
  const height = rect.y1 - rect.y0
  const nearest = (targets: number[], from: number[]) => {
    let best: number | null = null
    for (const target of targets) for (const edge of from) if (Math.abs(target - edge) <= pull && (best === null || Math.abs(target - edge) < Math.abs(best))) best = target - edge
    return best ?? 0
  }
  const shiftX = nearest(others.flatMap((other) => [other.x0, other.x1]), [rect.x0, rect.x1])
  const shiftY = nearest(others.flatMap((other) => [other.y0, other.y1]), [rect.y0, rect.y1])
  const x0 = Math.round((rect.x0 + shiftX) / STEP) * STEP
  const y0 = Math.round((rect.y0 + shiftY) / STEP) * STEP
  const snapped = { x0, y0, x1: x0 + width, y1: y0 + height }
  const over = others.some((other) => snapped.x0 < other.x1 - STEP / 2 && other.x0 < snapped.x1 - STEP / 2 && snapped.y0 < other.y1 - STEP / 2 && other.y0 < snapped.y1 - STEP / 2)
  return over ? null : snapped
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

/** The board's islands (the ground the base map is cut to), their names (over their top left corner) and seams, as
 * GeoJSON for ./style.ts boardStyle. */
export function boardShapes(board: Board) {
  const ring = (rect: Rect): LngLat[] => [at([rect.x0, rect.y0]), at([rect.x1, rect.y0]), at([rect.x1, rect.y1]), at([rect.x0, rect.y1]), at([rect.x0, rect.y0])]
  return {
    type: 'FeatureCollection' as const,
    features: [
      ...board.islands.map((island) => ({ type: 'Feature' as const, properties: { kind: 'island' }, geometry: { type: 'Polygon' as const, coordinates: [ring(boardRect(island))] } })),
      ...board.islands.flatMap((island) => (island.name ? [{ type: 'Feature' as const, properties: { kind: 'island-name', label: island.name }, geometry: { type: 'Point' as const, coordinates: at([boardRect(island).x0, boardRect(island).y0]) } }] : [])),
      ...board.seams.map((seam) => ({ type: 'Feature' as const, properties: { kind: 'seam' }, geometry: { type: 'LineString' as const, coordinates: seam.line } })),
      ...board.seams.map((seam) => ({ type: 'Feature' as const, properties: { kind: 'seam-label', label: seam.label, anchor: seam.anchor }, geometry: { type: 'Point' as const, coordinates: seam.at } })),
    ],
  }
}

type Located = { id: string; location: { lat: number; lon: number; origin?: { lat: number; lon: number }; outline?: [number, number][][] } | null }

/** The board for a map's buildings (null when none has a position): as its layout placed it, else arranged. */
export function boardOf(buildings: Located[], arrangement: Arrangement, layout: Layout | null = null): Board | null {
  const sites = buildings.flatMap((b) => (b.location ? [{ id: b.id, points: b.location.outline?.flat().length ? b.location.outline.flat() : [[b.location.lon, b.location.lat] as LngLat] }] : []))
  if (!sites.length) return null
  const islands = islandsOf(sites)
  const stored = matchSites(islands, layout?.sites ?? [])
  if (stored.some((site) => site && site.dx !== null && site.dy !== null)) return placeByLayout(islands, stored)
  return arrange(islands.map((island, i) => ({ ...island, name: stored[i]?.name ?? null })), arrangement)
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
