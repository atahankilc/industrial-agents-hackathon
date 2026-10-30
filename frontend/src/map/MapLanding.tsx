// Landing: the buildings with a real position (GET /buildings `location`, the kit's OpenStreetMap buildings) as pins
// on a city map; tap a pin or a row to open the building. Over the map: Steward's mark and wordmark (top left), and
// under it the search field, a pill (the card only appears once the list opens). A click in the field opens the list under it: every building, the ones on the map first, then the ones with
// no position; typing narrows it by name and chips by kind (campus, factory, home, …). Map: MapLibre with our own base style on OpenFreeMap's tiles (./style.ts), light or dark with
// the app theme, tilted, buildings extruded to their OSM height (streamed with the tiles, nothing stored). Pins and names are map layers drawn above, so names that would collide
// are dropped by the map itself.
// With a building open the map stays mounted under its screen (src/Root.tsx): it flies in to the building and then
// follows the model's camera (./bridge.ts), so in the city view the neighbours stay on screen and their pins can be
// tapped; shown alone, the building screen's own stage covers it. Closing the building flies back to where the map was
// when it was opened (every pin, if it was opened from a link).
// An organisation's map (`scoped`) is an island board instead of the world (./board.ts, docs/product/organizations.md
// phase 3): its sites as islands side by side on their own tiles (./boardTiles.ts), the buildings moved with them
// (src/Root.tsx), "you are here" only where it is on the board (standing on an island: the dot moved with it; else
// the nearest site and how far), "Create a building here" only on an island, at the real place under the tap. The map's editors "Arrange" it: an island dragged is pulled against its neighbours' edges
// (never onto one) and a tapped one is named; each change is saved at once (`onArrange`, the map's layout).

import maplibregl, { type GeoJSONSource, type GeoJSONSourceSpecification, type Map as MapLibreMap, type VectorTileSource } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { useAccess } from '../access/auth'
import { api, type Building, type BuildingKind, type ImportPlace } from '../api'
import { useTheme } from '../theme'
import { Wordmark } from '../brand/Wordmark'
import { outerRing, ringContains, TILE_BUILDINGS } from './geo'
import { applyBlocks, attachMap, FLAT_FOV, osmHeights, setTheme, toLngLat, type Origin } from './bridge'
import '../building/hud.css' // the HUD tokens (--hud-*) the panel shares with the building screen
import './map.css'
import { BUILDINGS_FROM_ZOOM, MODEL_TONES, boardStyle, mapStyle, mix, modelColours, modelTones } from './style'
import { at as worldAt, boardBounds, boardRect, boardShapes, changed, distanceLabel, dropAt, islandAt, layoutOf, overlaps, reshapeAt, toReal, whereOnBoard, worldX, worldY, type Board, type Edges, type Layout, type Rect } from './board'
import { boardTilesUrl, registerBoard } from './boardTiles'
import { reducedMotion } from '../motion'

// the list's kind chips, in this order; a chip shows only when some building has that kind
const KINDS: { kind: BuildingKind; label: string }[] = [
  { kind: 'campus', label: 'Campus' },
  { kind: 'factory', label: 'Factory' },
  { kind: 'home', label: 'Home' },
  { kind: 'real', label: 'Real' },
  { kind: 'saved', label: 'Saved' },
]
const MUNICH = { center: [11.575, 48.14] as [number, number], zoom: 10.5 }
const FIT_PADDING = { top: 80, right: 60, bottom: 80, left: 60 }
const PANEL_PX = 416 // wide screens: the list panel covers the map's left edge
const WIDE_PX = 900
const PITCH = 50
const FOV = 36.87 // MapLibre's own vertical field of view (degrees)
const FLY = { zoom: 17.6, pitch: 56, bearing: -45 } // close to where the model's first framing lands (src/plan/PlanView.tsx TILTED)
const FLY_MS = 1500
const PICK_ZOOM = 17 // a building picked in the list: close enough to see its block and tap it
const CALM_FLY_MS = 1000 // with "reduce motion" on: still a flight (the move tells you where you are), just shorter
const flyMs = () => (reducedMotion() ? CALM_FLY_MS : FLY_MS)
// pins in the HUD's ink, ringed in the ground colour, on a soft disc that marks them from afar (no glow)
const PIN = {
  light: { fill: '#111215', ring: '#F2F2EF', disc: '#111215', text: '#111215', halo: '#F2F2EF' },
  dark: { fill: '#F3F4F6', ring: '#0F1013', disc: '#F3F4F6', text: '#F3F4F6', halo: '#0F1013' },
}

// the layers a click opens a building from, and how far the pointer may miss them (px)
const HIT_LAYERS = ['pins', 'pin-names', 'pin-discs', 'model-blocks', 'model-footprints']
const MODEL_LAYERS = ['model-footprints', 'model-blocks', 'model-edges']
const HIT_SLOP = 14

/** `at`: the tapped point ([lng, lat]); the card opens there and follows it while the map moves */
// ours: `pick` (right click) — a version is chosen to act on (open, delete) instead of opened
type Card = ({ kind: 'osm'; place: ImportPlace } | { kind: 'ours'; ids: string[]; pick?: boolean }) & { at: [number, number] }

const LOCATE_DISMISSED = 'ml-locate-dismissed' // "Not now" on the location card, remembered per browser
const LOCATE_ALLOWED = 'ml-locate-allowed' // "Allow" on it: an iOS home screen app forgets the grant on every launch

type Located = Building & { location: NonNullable<Building['location']> }
/** light up a building's pin and block */
function hoverBuilding(map: MapLibreMap, id: string, on: boolean) {
  for (const source of ['buildings', 'models']) if (map.getSource(source)) map.setFeatureState({ source, id }, { hover: on })
}
/** keep a building's pin and block lit while it is the one picked in the list */
function selectBuilding(map: MapLibreMap, id: string, on: boolean) {
  for (const source of ['buildings', 'models']) if (map.getSource(source)) map.setFeatureState({ source, id }, { selected: on })
}
// a pin or block is lit while under the pointer or picked in the list
const LIT: maplibregl.ExpressionSpecification = [
  'any',
  ['boolean', ['feature-state', 'hover'], false],
  ['boolean', ['feature-state', 'selected'], false],
]

// the picked building's row opens it: "Open ›" inside the row, not a button of its own
const GO = (
  <span className="ml-go" aria-hidden>
    Open
    <svg viewBox="0 0 24 24" width="14" height="14"><path d="M9 6l6 6-6 6" /></svg>
  </span>
)

const nameOf = (b: Building) => b.name ?? b.id.split('/').pop() ?? b.id
const fold = (text: string) => text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase()
/** the building open on top of the map */
export type Focus = { id: string; origin: Origin }

/** Ease the map's field of view (a narrow one flattens its perspective to match the model's camera); a new ease
 * replaces one still running, so a fly-in and a fly-out never fight over it. */
const easing = new WeakMap<MapLibreMap, number>()
function easeFov(map: MapLibreMap, to: number, ms: number) {
  cancelAnimationFrame(easing.get(map) ?? 0)
  const from = map.getVerticalFieldOfView()
  if (ms <= 0 || from === to) return void map.setVerticalFieldOfView(to)
  const start = performance.now()
  const step = (now: number) => {
    const t = Math.min(1, (now - start) / ms)
    const k = t * t * (3 - 2 * t)
    map.setVerticalFieldOfView(from + (to - from) * k)
    if (t < 1) easing.set(map, requestAnimationFrame(step))
  }
  easing.set(map, requestAnimationFrame(step))
}

// an organisation's map before its buildings are in: the table alone, not a flash of the world
const NO_ISLANDS: Board = { key: 'none', islands: [], seams: [], byHand: false }
function styleFor(dark: boolean, scoped: boolean, board: Board | null) {
  if (!scoped) return mapStyle(dark)
  const shown = board ?? NO_ISLANDS
  registerBoard(shown)
  return boardStyle(dark, boardTilesUrl(shown), boardShapes(shown))
}

/** The board's own "you are here" button (MapLibre's would show where the user really is, off the board), dressed
 * as MapLibre's. */
class BoardLocate implements maplibregl.IControl {
  private box: HTMLDivElement | null = null
  private press: () => void
  constructor(press: () => void) {
    this.press = press
  }
  onAdd() {
    const box = document.createElement('div')
    box.className = 'maplibregl-ctrl maplibregl-ctrl-group'
    const button = document.createElement('button')
    button.type = 'button'
    button.className = 'maplibregl-ctrl-geolocate'
    button.title = 'Where am I on this map'
    button.setAttribute('aria-label', 'Where am I on this map')
    button.innerHTML = '<span class="maplibregl-ctrl-icon" aria-hidden="true"></span>'
    button.addEventListener('click', () => this.press())
    box.append(button)
    this.box = box
    return box
  }
  onRemove() {
    this.box?.remove()
  }
}

/** "Version 2" for a saved building whose name was taken (user/<slug>-2), "Version 1" for the first save. */
const versionOf = (id: string) => (id.startsWith('user/') ? `Version ${/-(\d+)$/.exec(id)?.[1] ?? 1}` : null)

// an island dragged this close (px) to another's edge meets it
const PULL_PX = 14
// an island's edge or corner is taken (to draw its area) this close (px): a finger needs more room than a pointer
const EDGE_PX = { mouse: 10, touch: 22 }

/** the island edges (and so corners) within `reach` (world units) of a board point, if any; where two islands meet,
 * the edge of the one the point is on */
function edgesAt(board: Board, [x, y]: [number, number], reach: number): { index: number; edges: Edges } | null {
  const found: { index: number; edges: Edges; inside: boolean }[] = []
  for (const [index, island] of board.islands.entries()) {
    const r = boardRect(island)
    if (x < r.x0 - reach || x > r.x1 + reach || y < r.y0 - reach || y > r.y1 + reach) continue
    const edges = { left: Math.abs(x - r.x0) <= reach, right: Math.abs(x - r.x1) <= reach, top: Math.abs(y - r.y0) <= reach, bottom: Math.abs(y - r.y1) <= reach }
    if (edges.left || edges.right || edges.top || edges.bottom) found.push({ index, edges, inside: x >= r.x0 && x <= r.x1 && y >= r.y0 && y <= r.y1 })
  }
  const best = found.find((candidate) => candidate.inside) ?? found[0]
  return best ? { index: best.index, edges: best.edges } : null
}
const CURSORS: Record<string, string> = { left: 'ew-resize', right: 'ew-resize', top: 'ns-resize', bottom: 'ns-resize', 'left top': 'nwse-resize', 'right bottom': 'nwse-resize', 'right top': 'nesw-resize', 'left bottom': 'nesw-resize' }
const cursorOf = (edges: Edges) => CURSORS[(['left', 'right', 'top', 'bottom'] as const).filter((edge) => edges[edge]).join(' ')] ?? 'move'

export function MapLanding({ buildings, error, focus, scope = null, scoped = false, board = null, onArrange, onOpen, onImport, onDeleted, onLeaveScope, onOpenMap }: {
  buildings: Building[] | null
  error: string | null
  /** an organisation's map (?map=, docs/product/organizations.md): its name and org head the map instead of Steward's */
  scope?: { name: string; org: string | null; orgSlug?: string; verified?: boolean } | null
  /** the map is an organisation's (fixed for this map's life: Root keys it by the map) and shows `board` once known;
   * `buildings` are then already on the board */
  scoped?: boolean
  board?: Board | null
  /** the map's editors moved or named an island: the new layout to store (absent: the viewer may not arrange) */
  onArrange?: (layout: Layout) => Promise<void>
  focus: Focus | null
  onOpen: (id: string) => void
  onImport: (place?: ImportPlace) => void
  onDeleted: () => void
  /** back to the main map from an organisation's map */
  onLeaveScope?: () => void
  /** an org's badge tapped on the main map: open that org's public map (Building `badge`) */
  onOpenMap?: (slug: string) => void
}) {
  const access = useAccess() // access mode: only the admin creates buildings (an import is a paid Creator run)
  const { dark } = useTheme()
  setTheme(dark) // the blocks the bridge draws around an open building take the map's colours
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const openRef = useRef(onOpen)
  openRef.current = onOpen
  const focusRef = useRef(focus)
  focusRef.current = focus
  const boardRef = useRef(board)
  boardRef.current = board
  // arranging the board: drag islands, tap one to name it
  const [arranging, setArranging] = useState(false)
  const arrangingRef = useRef(arranging)
  arrangingRef.current = arranging && Boolean(onArrange)
  // a change the backend refused is put back by Root and said in the bar
  const [arrangeError, setArrangeError] = useState<string | null>(null)
  const save = (layout: Layout) => {
    setArrangeError(null)
    onArrange?.(layout).catch((reason) => setArrangeError(reason instanceof Error ? reason.message : String(reason)))
  }
  const arrangeRef = useRef(save)
  arrangeRef.current = save
  const [naming, setNaming] = useState<{ index: number; name: string; x: number; y: number } | null>(null)
  const namingRef = useRef(setNaming)
  const geolocateRef = useRef<maplibregl.GeolocateControl | null>(null)
  // the building picked in the list: the map flies to it and keeps it lit; a tap on it on the map opens it
  const [picked, setPicked] = useState<string | null>(null)
  const pickRef = useRef(setPicked)
  // a tap on a building that is not one of ours (create one there), or on our model blocks (open / delete)
  const [card, setCard] = useState<Card | null>(null)
  // "Delete" asks once more in place (no browser dialog); a failure is said in the card
  const [deleting, setDeleting] = useState<'ask' | 'busy' | string | null>(null)
  useEffect(() => setDeleting(null), [card])
  // and in access mode on a verified organisation's map, its editors (for that organisation)
  const orgRole = scope?.orgSlug ? access.orgs[scope.orgSlug] : undefined
  const canCreate = !access.mode || access.admin || (Boolean(scope?.verified) && (orgRole === 'editor' || orgRole === 'owner'))
  const canCreateRef = useRef(canCreate)
  canCreateRef.current = canCreate
  const cardOpenRef = useRef(false)
  cardOpenRef.current = card !== null
  const [askLocation, setAskLocation] = useState(false)
  // the panel: the search field; a click in the field opens the list under it, the map, Esc, × or
  // picking a building closes it again. The closed card's height (its top part) is measured: the panel animates
  // between it and the full height, and on narrow screens the map's controls sit above it.
  const [listOpen, setListOpen] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  const top = useRef<HTMLDivElement>(null)
  const [topHeight, setTopHeight] = useState<number | null>(null)
  useEffect(() => {
    const element = top.current
    if (!element) return
    const observer = new ResizeObserver(() => setTopHeight(element.offsetHeight))
    observer.observe(element)
    return () => observer.disconnect()
  }, [])
  const closeList = () => {
    setListOpen(false)
    input.current?.blur()
  }
  // "/" puts the cursor in the search field (not while a building is open over the map)
  useEffect(() => {
    if (focus) return
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null
      if (event.key !== '/' || target?.closest('input, textarea, [contenteditable="true"]')) return
      event.preventDefault()
      input.current?.focus()
    }
    addEventListener('keydown', onKey)
    return () => removeEventListener('keydown', onKey)
  }, [focus])
  // back from a building: the card closed, the map in front
  useEffect(() => {
    if (focus) setListOpen(false)
  }, [focus])

  const located = useMemo(
    () =>
      (buildings ?? [])
        .filter((b): b is Located => Boolean(b.location))
        .sort((a, b) => nameOf(a).localeCompare(nameOf(b), undefined, { numeric: true })),
    [buildings],
  )
  // every other building has no position: listed after the ones on the map
  const elsewhere = useMemo(
    () => (buildings ?? []).filter((b) => !b.location).sort((a, b) => nameOf(a).localeCompare(nameOf(b), undefined, { numeric: true })),
    [buildings],
  )
  // the search field: by name only, accents and case ignored, every word must match
  const [query, setQuery] = useState('')
  const words = fold(query).split(/\s+/).filter(Boolean)
  // the kind chips: one at a time, none = every kind
  const [kind, setKind] = useState<BuildingKind | null>(null)
  const kinds = KINDS.filter((k) => buildings?.some((b) => b.kind === k.kind))
  const named = (b: Building) => (!kind || b.kind === kind) && words.every((w) => fold(nameOf(b)).includes(w))
  const shownLocated = located.filter(named)
  const shownElsewhere = elsewhere.filter(named)
  const shown = [...shownLocated, ...shownElsewhere]
  const nameOfId = (id: string) => {
    const building = buildings?.find((item) => item.id === id)
    return building ? nameOf(building) : id
  }
  const addressOf = (id: string) => buildings?.find((item) => item.id === id)?.location?.address ?? null
  const badgeOf = (id: string) => buildings?.find((item) => item.id === id)?.badge ?? null
  const pickedBadge = picked ? badgeOf(picked) : null
  const outlineOf = (id: string) => buildings?.find((item) => item.id === id)?.location?.outline?.[0] ?? null

  // the map: created once; its style follows the theme (a style swap drops our layers, so they go back on style.load)
  useEffect(() => {
    const map = new maplibregl.Map({
      container: container.current!,
      style: styleFor(dark, scoped, board),
      ...MUNICH,
      pitch: PITCH,
      maxPitch: 75, // the model tilts to 69° (src/plan/PlanView.tsx MAX_POLAR)
      attributionControl: { compact: true },
    })
    // zoom about twice MapLibre's default speed (wheel 1/450, trackpad 1/100)
    map.scrollZoom.setWheelZoomRate(1 / 220)
    map.scrollZoom.setZoomRate(1 / 50)
    // the compact credits start open, a two-line bar over the map on a phone: closed to their (i) button
    map.once('idle', () => container.current?.querySelector('.maplibregl-ctrl-attrib')?.classList.remove('maplibregl-compact-show'))
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'bottom-right')
    // the viewer's own position as a dot (the browser asks first; it needs https or localhost); on a board, our own
    // button and dot (below)
    if (!scoped) {
      const geolocate = new maplibregl.GeolocateControl({ positionOptions: { enableHighAccuracy: true }, trackUserLocation: true, fitBoundsOptions: { maxZoom: 16 } })
      map.addControl(geolocate, 'bottom-right')
      geolocateRef.current = geolocate
    } else map.addControl(new BoardLocate(() => locateRef.current('tap')), 'bottom-right')
    // a building opens from its pin, its name, the halo round the pin or its block, and the pointer may miss by a
    // finger's width (HIT_SLOP px): the pin alone is too small a target
    const hit = (point: maplibregl.Point) => {
      const layers = HIT_LAYERS.filter((layer) => map.getLayer(layer))
      if (!layers.length) return null
      const box: [maplibregl.PointLike, maplibregl.PointLike] = [
        [point.x - HIT_SLOP, point.y - HIT_SLOP],
        [point.x + HIT_SLOP, point.y + HIT_SLOP],
      ]
      // a block right under the pointer wins; else the nearest pin (neighbouring pins and their halos overlap); a block
      // only within reach comes last
      const distance = (feature: maplibregl.MapGeoJSONFeature) =>
        feature.geometry.type === 'Point'
          ? point.dist(map.project(feature.geometry.coordinates as [number, number]))
          : Infinity
      const blocks = layers.filter((layer) => layer.startsWith('model-'))
      const under = blocks.length ? map.queryRenderedFeatures(point, { layers: blocks })[0] : undefined
      const id = (under ?? map.queryRenderedFeatures(box, { layers }).sort((a, b) => distance(a) - distance(b))[0])?.properties?.id
      return typeof id === 'string' ? id : null
    }
    let hovered: string | null = null
    // our model blocks under a point (several = versions standing on one place)
    const oursAt = (point: maplibregl.Point) => {
      const blocks = MODEL_LAYERS.filter((layer) => layer !== 'model-edges' && map.getLayer(layer))
      return blocks.length
        ? [...new Set(map.queryRenderedFeatures(point, { layers: blocks }).map((feature) => feature.properties?.id))]
            .filter((id): id is string => typeof id === 'string')
        : []
    }
    // left click: an open card just closes; else a pin or a model opens (a choice when versions share the place)
    map.on('click', (event) => {
      setListOpen(false) // a tap on the map closes the list first
      input.current?.blur()
      if (arrangingRef.current) return // taps name islands (below)
      if (cardOpenRef.current) return setCard(null)
      const at: [number, number] = [event.lngLat.lng, event.lngLat.lat]
      const ours = oursAt(event.point)
      if (ours.length > 1) return setCard({ kind: 'ours', ids: ours, at })
      const id = ours[0] ?? hit(event.point)
      if (id) openRef.current(id)
      else pickRef.current(null)
    })
    // right click: "Create a building here" on an OpenStreetMap building or open ground; on ours: open / delete
    map.on('contextmenu', (event) => {
      event.preventDefault()
      const at: [number, number] = [event.lngLat.lng, event.lngLat.lat]
      const ours = oursAt(event.point)
      const pinned = ours.length ? null : hit(event.point)
      if (ours.length || pinned) return setCard({ kind: 'ours', ids: ours.length ? ours : [pinned!], at, pick: true })
      // on a board only on an island (open table is nowhere)
      if (!canCreateRef.current || (boardRef.current && !islandAt(boardRef.current, at))) return setCard(null)
      // the building whose footprint holds the ground point under the cursor (tile data, not the tilted 3D blocks), else
      // the block drawn under the cursor
      const onGround = map.querySourceFeatures('openmaptiles', { sourceLayer: 'building' })
        .find((feature) => { const part = outerRing(feature.geometry as { type: string; coordinates?: unknown }, at); return part ? ringContains(part, at) : false })
      const tiles = TILE_BUILDINGS.filter((layer) => map.getLayer(layer))
      const tile = onGround ?? (tiles.length ? map.queryRenderedFeatures(event.point, { layers: tiles })[0] : undefined)
      const ring = tile ? outerRing(tile.geometry as { type: string; coordinates?: unknown }, at) : null
      const name = typeof tile?.properties?.name === 'string' ? tile.properties.name : undefined
      setCard({ kind: 'osm', place: ring ? { ring, name } : { point: at }, at })
    })
    // arranging: an island under the pointer goes with it (the map does not pan), its outline shown where it would land
    // (red where it may not: on another island); let go, it lands there; a tap without a move names it. Taken by an
    // edge or corner, the island's area is drawn instead: those edges follow the pointer
    let drag: { index: number; from: [number, number]; rect: Rect; to: Rect | null; moved: boolean; start: maplibregl.Point; edges: Edges | null } | null = null
    const ghost = (rect: Rect | null, ok: boolean) => {
      const ring = rect ? [[rect.x0, rect.y0], [rect.x1, rect.y0], [rect.x1, rect.y1], [rect.x0, rect.y1], [rect.x0, rect.y0]].map((p) => worldAt(p as [number, number])) : []
      const data: GeoJSONSourceSpecification['data'] = { type: 'Feature', properties: { ok }, geometry: { type: 'Polygon', coordinates: ring.length ? [ring] : [] } }
      const source = map.getSource('board-drag') as GeoJSONSource | undefined
      if (source) return source.setData(data)
      if (!rect) return
      const ink = document.documentElement.dataset.theme === 'light' ? '#111318' : '#FFFFFF'
      const colour: maplibregl.ExpressionSpecification = ['case', ['get', 'ok'], ink, '#E5484D']
      map.addSource('board-drag', { type: 'geojson', data })
      map.addLayer({ id: 'board-drag-fill', type: 'fill', source: 'board-drag', paint: { 'fill-color': colour, 'fill-opacity': 0.12 } })
      map.addLayer({ id: 'board-drag-line', type: 'line', source: 'board-drag', paint: { 'line-color': colour, 'line-width': 2, 'line-dasharray': [2, 1.5] } })
    }
    const grab = (event: maplibregl.MapMouseEvent | maplibregl.MapTouchEvent) => {
      const current = boardRef.current
      if (!arrangingRef.current || !current || ('points' in event && event.points.length > 1)) return
      const from: [number, number] = [worldX(event.lngLat.lng), worldY(event.lngLat.lat)]
      const reach = EDGE_PX['points' in event ? 'touch' : 'mouse'] / (512 * 2 ** map.getZoom())
      const edge = edgesAt(current, from, reach)
      const island = edge ? current.islands[edge.index] : islandAt(current, [event.lngLat.lng, event.lngLat.lat])
      if (!island) return
      event.preventDefault() // no pan: the island moves instead
      const rect = boardRect(island)
      drag = { index: current.islands.indexOf(island), from, rect, to: rect, moved: false, start: event.point, edges: edge?.edges ?? null }
    }
    const move = (event: maplibregl.MapMouseEvent | maplibregl.MapTouchEvent) => {
      const current = boardRef.current
      if (!drag || !current) return
      if (!drag.moved && event.point.dist(drag.start) < 5) return
      drag.moved = true
      const dx = worldX(event.lngLat.lng) - drag.from[0]
      const dy = worldY(event.lngLat.lat) - drag.from[1]
      const pull = PULL_PX / (512 * 2 ** map.getZoom()) // world units per px at this zoom
      const { edges, rect } = drag
      const moved = edges
        ? { x0: rect.x0 + (edges.left ? dx : 0), y0: rect.y0 + (edges.top ? dy : 0), x1: rect.x1 + (edges.right ? dx : 0), y1: rect.y1 + (edges.bottom ? dy : 0) }
        : { x0: rect.x0 + dx, y0: rect.y0 + dy, x1: rect.x1 + dx, y1: rect.y1 + dy }
      drag.to = edges ? reshapeAt(current, drag.index, moved, edges, pull) : dropAt(current, drag.index, moved, pull)
      ghost(drag.to ?? moved, drag.to !== null)
    }
    const drop = () => {
      const current = boardRef.current
      const done = drag
      drag = null
      if (!done || !current) return
      ghost(null, true)
      if (!done.moved) {
        const { x, y } = map.project(worldAt([(done.rect.x0 + done.rect.x1) / 2, done.rect.y0]))
        return namingRef.current({ index: done.index, name: current.islands[done.index].name ?? '', x, y })
      }
      if (done.to) arrangeRef.current(layoutOf(changed(current, done.index, done.edges ? { area: done.to } : { rect: done.to })))
    }
    map.on('mousedown', grab)
    map.on('touchstart', grab)
    map.on('mousemove', move)
    map.on('touchmove', move)
    map.on('mouseup', drop)
    map.on('touchend', drop)
    map.on('touchcancel', drop)
    map.on('mousemove', (event) => {
      if (arrangingRef.current) {
        const current = boardRef.current
        const edge = current && !drag ? edgesAt(current, [worldX(event.lngLat.lng), worldY(event.lngLat.lat)], EDGE_PX.mouse / (512 * 2 ** map.getZoom())) : null
        map.getCanvas().style.cursor = drag ? (drag.edges ? cursorOf(drag.edges) : 'grabbing')
          : edge ? cursorOf(edge.edges) : current && islandAt(current, [event.lngLat.lng, event.lngLat.lat]) ? 'grab' : ''
        return
      }
      const id = hit(event.point)
      if (id === hovered) return
      if (hovered) hoverBuilding(map, hovered, false)
      if (id) hoverBuilding(map, id, true)
      hovered = id
      map.getCanvas().style.cursor = id ? 'pointer' : ''
    })
    mapRef.current = map
    attachMap(map)
    // a new map (React's dev double mount makes two) has flown nowhere and framed nothing yet
    flownTo.current = null
    framed.current = false
    // a building already open: the flat field of view, once the style is in (loading can reset the camera)
    map.on('load', () => focusRef.current && map.setVerticalFieldOfView(FLAT_FOV))
    if (import.meta.env.DEV) Object.assign(window, { __map: map })
    return () => {
      attachMap(null)
      map.remove()
      mapRef.current = null
      geolocateRef.current = null
    }
    // the style is swapped by the effect below, not by recreating the map
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    const colours = PIN[dark ? 'dark' : 'light']
    const data: GeoJSONSourceSpecification['data'] = {
      type: 'FeatureCollection',
      features: located.map((b) => ({
        type: 'Feature',
        properties: { id: b.id, name: nameOf(b), org: b.badge?.name ?? '' },
        geometry: { type: 'Point', coordinates: [b.location.lon, b.location.lat] },
      })),
    }
    const addPins = () => {
      const source = map.getSource('buildings') as GeoJSONSource | undefined
      if (source) {
        source.setData(data)
        modelsSource()?.setData(modelData())
        return
      }
      // the buildings you can open, as blocks in the accent: their kit footprint, as tall as the kit or the OSM block
      // it stands in, whichever is taller (so the accent wraps the grey block); flat below the zoom blocks rise at
      // (each in its tone, the one under the pointer lit up, every footprint traced: see modelColours)
      const models = modelColours(dark)
      const tall: maplibregl.ExpressionSpecification = ['+', ['max', ['get', 'height'], ['get', 'osm']], 0.4]
      const lit = LIT
      const byTone = (pick: (tone: number) => maplibregl.ExpressionSpecification | string) =>
        ['match', ['get', 'tone'], ...MODEL_TONES.slice(1).flatMap((_, i) => [i + 1, pick(i + 1)]), pick(0)] as unknown as maplibregl.ExpressionSpecification
      // the building being opened breathes, lit or not, toward a paler accent until its model is there (bridge.ts
      // `pulse`)
      const breathing = (base: maplibregl.ExpressionSpecification): maplibregl.ExpressionSpecification =>
        ['interpolate', ['linear'], ['number', ['feature-state', 'pulse'], 0], 0, base, 1, mix(models.hover, 0.25)]
      map.addSource('models', { type: 'geojson', data: modelData(), promoteId: 'id' })
      // the flat footprint and its edge lie on the ground under the OSM blocks, so the blocks in front hide them
      const ground = map.getLayer('buildings-3d') ? 'buildings-3d' : undefined
      map.addLayer({
        id: 'model-footprints',
        type: 'fill',
        source: 'models',
        minzoom: 12,
        maxzoom: BUILDINGS_FROM_ZOOM + 0.6,
        paint: { 'fill-color': breathing(['case', lit, models.hover, byTone((tone) => modelColours(dark, tone).wall)]) },
      }, ground)
      map.addLayer({
        id: 'model-blocks',
        type: 'fill-extrusion',
        source: 'models',
        minzoom: BUILDINGS_FROM_ZOOM,
        paint: {
          'fill-extrusion-color': breathing([
            'case', lit, models.hover,
            byTone((tone) => ['interpolate', ['linear'], tall, 0, modelColours(dark, tone).wall, 45, modelColours(dark, tone).roof]),
          ]),
          'fill-extrusion-height': ['interpolate', ['linear'], ['zoom'], BUILDINGS_FROM_ZOOM, 0, BUILDINGS_FROM_ZOOM + 0.6, tall],
          'fill-extrusion-opacity': 0.95,
          'fill-extrusion-vertical-gradient': true,
        },
      })
      map.addLayer({
        id: 'model-edges',
        type: 'line',
        source: 'models',
        minzoom: 12,
        paint: { 'line-color': models.edge, 'line-width': ['interpolate', ['linear'], ['zoom'], 12, 0.8, 17, 1.8], 'line-opacity': 0.9 },
      }, ground)
      map.addSource('buildings', { type: 'geojson', data, promoteId: 'id' })
      const hover = LIT
      map.addLayer({
        id: 'pin-discs',
        type: 'circle',
        source: 'buildings',
        paint: { 'circle-radius': ['case', hover, 22, 15], 'circle-color': colours.disc, 'circle-opacity': ['case', hover, 0.16, 0.1], 'circle-pitch-alignment': 'map' },
      })
      map.addLayer({
        id: 'pins',
        type: 'circle',
        source: 'buildings',
        paint: { 'circle-radius': ['case', hover, 7.5, 5.5], 'circle-color': colours.fill, 'circle-stroke-color': colours.ring, 'circle-stroke-width': 2 },
      })
      map.addLayer({
        id: 'pin-names',
        type: 'symbol',
        source: 'buildings',
        layout: {
          // an org's building: its org under the name, smaller (the main map's badge)
          'text-field': ['case', ['==', ['get', 'org'], ''], ['get', 'name'],
            ['format', ['get', 'name'], {}, '\n', {}, ['get', 'org'], { 'font-scale': 0.85, 'text-font': ['literal', ['Noto Sans Regular']] }]],
          'text-font': ['Noto Sans Bold'],
          'text-size': 12,
          'text-letter-spacing': 0.02,
          'text-anchor': 'top',
          'text-offset': [0, 0.9],
          'text-max-width': 12,
          'text-optional': true,
        },
        paint: { 'text-color': colours.text, 'text-halo-color': colours.halo, 'text-halo-width': 1.8 },
      })
    }
    // isStyleLoaded() stays false while tiles and glyphs load, long after style.load has fired: so try now, and if
    // the style really is not ready, again once the map is idle
    const tryPins = () => {
      try {
        addPins()
      } catch {
        map.once('idle', tryPins)
      }
    }
    // the OSM blocks' heights arrive with the tiles
    const modelsSource = () => map.getSource('models') as GeoJSONSource | undefined
    const heights = { key: '' }
    const tones = modelTones(located.map((b) => b.location.outline ?? []))
    const modelData = (osm = osmHeights(located.map((b) => b.location.outline ?? []))): GeoJSONSourceSpecification['data'] => {
      heights.key = osm.join(',')
      return {
        type: 'FeatureCollection',
        features: located.map((b, i) => ({
          type: 'Feature',
          properties: { id: b.id, height: b.location.height_m ?? 0, osm: osm[i] ?? 0, tone: tones[i] ?? 0 },
          geometry: { type: 'MultiPolygon', coordinates: (b.location.outline ?? []).map((ring) => [ring]) },
        })),
      }
    }
    // only once new tiles have arrived: the map goes idle after every move, and reading every block costs a frame or more
    let tiles = true
    const onTiles = (event: maplibregl.MapSourceDataEvent) => {
      if (event.sourceId === 'openmaptiles') tiles = true
    }
    const updateHeights = () => {
      const source = modelsSource()
      if (!source || !tiles) return
      tiles = false
      const osm = osmHeights(located.map((b) => b.location.outline ?? []))
      if (osm.join(',') !== heights.key) source.setData(modelData(osm))
    }
    tryPins()
    map.on('sourcedata', onTiles)
    map.on('idle', updateHeights)
    map.on('style.load', addPins)
    map.on('style.load', hideFocused)
    map.on('style.load', applyBlocks)
    return () => {
      map.off('sourcedata', onTiles)
      map.off('idle', updateHeights)
      map.off('style.load', addPins)
      map.off('style.load', hideFocused)
      map.off('style.load', applyBlocks)
      map.off('idle', tryPins)
    }
    // hideFocused reads the focus from its ref
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [located, dark])

  // the open building's pin and accent block give way to the model (its OSM blocks too: the screen hides them, ./bridge.ts)
  const hideFocused = () => {
    const map = mapRef.current
    if (!map) return
    const id = focusRef.current?.id
    const pinFilter: maplibregl.FilterSpecification | null = id ? ['!=', ['get', 'id'], id] : null
    for (const layer of ['pin-discs', 'pins', 'pin-names', ...MODEL_LAYERS]) if (map.getLayer(layer)) map.setFilter(layer, pinFilter)
  }

  // fly in to the open building (or jump, if the map just appeared under it), flattening the perspective so the
  // model's camera can take over; fly back to where the map was when it closes (to every pin, if there is no such view)
  const focusId = focus?.id ?? null
  const flownTo = useRef<string | null>(null)
  // where the map was when a building was opened from it: closing the building flies back there
  const before = useRef<maplibregl.CameraOptions | null>(null)
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    const was = flownTo.current
    flownTo.current = focusId
    const current = focusRef.current
    if (current) {
      const first = !was && !map.loaded() && !framed.current
      // (opened from a link, the map has not been looked at yet: closing frames every pin instead)
      if (!was) before.current = first ? null : { center: map.getCenter(), zoom: map.getZoom(), pitch: map.getPitch(), bearing: map.getBearing() }
      framed.current = true
      const ms = first ? 0 : flyMs()
      const camera = { center: toLngLat(current.origin, 0, 0), ...FLY }
      if (ms) map.flyTo({ ...camera, duration: ms, essential: true })
      else map.jumpTo(camera)
      easeFov(map, FLAT_FOV, ms * 0.8)
      hideFocused()
      return
    }
    if (!was) return
    const bounds = boardRef.current ? boardBounds(boardRef.current) : pinBounds(located)
    const ms = flyMs()
    const back = before.current
    before.current = null
    if (back) map.flyTo({ ...back, duration: ms, essential: true })
    else if (bounds) {
      const camera = map.cameraForBounds(bounds, { padding: fitPadding(), maxZoom: 15 })
      if (camera) map.flyTo({ ...camera, pitch: PITCH, bearing: 0, duration: ms, essential: true })
    }
    easeFov(map, FOV, ms)
    hideFocused()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusId])

  // theme change or new islands: swap the base style (pins are re-added on style.load above)
  const styleKey = `${dark}|${board?.key ?? ''}`
  const shownStyle = useRef(styleKey)
  const shownDark = useRef(dark)
  useEffect(() => {
    const map = mapRef.current
    if (!map || shownStyle.current === styleKey) return
    const hadIslands = !shownStyle.current.endsWith('|')
    shownStyle.current = styleKey
    const tiles = map.getSource('openmaptiles') as VectorTileSource | undefined
    // islands moved: new tiles and shapes in the same style (a style swap would blink every layer); the first islands
    // get a style of their own (the empty board's may still be loading, and would keep its tiles)
    if (hadIslands && dark === shownDark.current && board && tiles?.setTiles && map.getSource('board')) {
      registerBoard(board)
      tiles.setTiles([boardTilesUrl(board)])
      return
    }
    shownDark.current = dark
    map.setStyle(styleFor(dark, scoped, board), { diff: false })
    // board is read with its key
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [styleKey])
  // while arranging, every island's outline and corners are drawn, so it is clear what can be taken
  useEffect(() => {
    const map = mapRef.current
    if (!map || !scoped) return
    const shown = arranging && onArrange && board && !focus ? board : null
    const corners = (shown?.islands ?? []).flatMap((island) => {
      const r = boardRect(island)
      return [[r.x0, r.y0], [r.x1, r.y0], [r.x1, r.y1], [r.x0, r.y1]].map((p) => worldAt(p as [number, number]))
    })
    const rings = (shown?.islands ?? []).map((island) => {
      const r = boardRect(island)
      return [[r.x0, r.y0], [r.x1, r.y0], [r.x1, r.y1], [r.x0, r.y1], [r.x0, r.y0]].map((p) => worldAt(p as [number, number]))
    })
    const data: GeoJSONSourceSpecification['data'] = {
      type: 'FeatureCollection',
      features: [
        ...rings.map((ring) => ({ type: 'Feature' as const, properties: {}, geometry: { type: 'LineString' as const, coordinates: ring } })),
        ...corners.map((point) => ({ type: 'Feature' as const, properties: {}, geometry: { type: 'Point' as const, coordinates: point } })),
      ],
    }
    const place = () => {
      const source = map.getSource('board-handles') as GeoJSONSource | undefined
      if (source) return source.setData(data)
      if (!shown) return
      const ink = dark ? '#FFFFFF' : '#111318'
      map.addSource('board-handles', { type: 'geojson', data })
      map.addLayer({ id: 'board-handle-edges', type: 'line', source: 'board-handles', filter: ['==', ['geometry-type'], 'LineString'], paint: { 'line-color': ink, 'line-width': 1.5, 'line-opacity': 0.7 } })
      map.addLayer({ id: 'board-handle-corners', type: 'circle', source: 'board-handles', filter: ['==', ['geometry-type'], 'Point'], paint: { 'circle-radius': 5, 'circle-color': dark ? '#0F1013' : '#FFFFFF', 'circle-stroke-color': ink, 'circle-stroke-width': 2 } })
    }
    try {
      place()
    } catch {
      map.once('idle', place) // the style is still coming in
    }
    // (a theme change swaps the style and drops the layers: `dark` brings them back)
  }, [arranging, onArrange, board, focus, dark, scoped])

  // names and seams follow the board (a name alone keeps the key)
  useEffect(() => {
    const source = mapRef.current?.getSource('board') as GeoJSONSource | undefined
    if (board && source) source.setData(boardShapes(board))
  }, [board])
  // the camera stays over the board, with room round it to tilt and turn
  useEffect(() => {
    const map = mapRef.current
    if (map && scoped) map.setMaxBounds(board ? boardBounds(board, 1) : null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [board?.key])

  /** a place tapped on a board, back where it really is (the import stands the building there) */
  const realPlace = (place: ImportPlace, at: [number, number]): ImportPlace => {
    const island = boardRef.current ? islandAt(boardRef.current, at) : null
    if (!island) return place
    return 'ring' in place ? { ...place, ring: place.ring.map((point) => toReal(island, point)) } : { ...place, point: toReal(island, place.point) }
  }

  // the card sits at the tapped point (above it, below when there is no room), following it as the map moves; on narrow
  // screens it stays a bottom sheet (map.css)
  const [cardXY, setCardXY] = useState<{ x: number; y: number; below: boolean } | null>(null)
  useEffect(() => {
    const map = mapRef.current
    if (!map || !card) return setCardXY(null)
    const place = () => {
      const { x, y } = map.project(card.at)
      const width = map.getContainer().clientWidth
      setCardXY({ x: Math.min(Math.max(x, 200), width - 200), y, below: y < 300 })
    }
    place()
    map.on('move', place)
    return () => {
      map.off('move', place)
    }
  }, [card])
  const narrow = typeof window !== 'undefined' && window.matchMedia('(max-width: 899px)').matches

  // the tapped building's outline while its card is open (what "Create a building here" refers to)
  useEffect(() => {
    const map = mapRef.current
    if (!map || !map.isStyleLoaded()) return
    const ring = card?.kind === 'osm' && 'ring' in card.place ? card.place.ring : card?.kind === 'ours' ? outlineOf(card.ids[0]) : null
    const data = { type: 'Feature' as const, properties: {}, geometry: { type: 'Polygon' as const, coordinates: ring ? [ring] : [] } }
    const source = map.getSource('picked') as GeoJSONSource | undefined
    if (source) source.setData(data)
    else {
      map.addSource('picked', { type: 'geojson', data })
      map.addLayer({ id: 'picked-fill', type: 'fill', source: 'picked', paint: { 'fill-color': dark ? '#FFFFFF' : '#111318', 'fill-opacity': 0.18 } })
      map.addLayer({ id: 'picked-line', type: 'line', source: 'picked', paint: { 'line-color': dark ? '#FFFFFF' : '#111318', 'line-width': 2.5, 'line-opacity': 0.95 } })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [card, dark])

  // frame every pin once they are known, clear of the list panel on wide screens (not while a building is open)
  const framed = useRef(false)
  useEffect(() => {
    const map = mapRef.current
    const bounds = boardRef.current ? boardBounds(boardRef.current) : pinBounds(located)
    if (!map || framed.current || !bounds) return
    framed.current = true
    map.fitBounds(bounds, { pitch: PITCH, padding: fitPadding(), maxZoom: 15, duration: 0 })
  }, [located])

  // location on open: already allowed → show it; not asked yet → our card first, so a "no" is ours to take and the
  // browser's own prompt (which can stick as a denial) only follows a tap on Allow; denied → stay quiet. Opened into a
  // building (a reload or a link), this waits until the map is first shown, then runs once
  const locateAsked = useRef(false)
  const locate = () => {
    if (scoped) return locateOnBoard('auto')
    const map = mapRef.current
    const geolocate = geolocateRef.current
    if (!map || !geolocate) return
    if (map.loaded()) geolocate.trigger()
    else map.once('load', () => geolocate.trigger())
  }
  // on a board: the browser's position, watched, shown where it is on the board (./board.ts whereOnBoard). Started
  // like the main map's dot (allowed before) or by the button; the map flies to the dot, and after a tap on the
  // button, when the user is on no island, to the nearest one
  const [fix, setFix] = useState<{ at: [number, number]; flyTo: 'auto' | 'tap' | null } | null>(null)
  const [locateError, setLocateError] = useState<string | null>(null)
  const [nearClosed, setNearClosed] = useState(false)
  const watching = useRef<number | null>(null)
  const locateOnBoard = (why: 'auto' | 'tap') => {
    setNearClosed(false)
    setLocateError(null)
    if (watching.current !== null) return setFix((last) => (last ? { ...last, flyTo: why } : last))
    if (!('geolocation' in navigator)) return setLocateError('This browser cannot tell where you are.')
    let first = true
    watching.current = navigator.geolocation.watchPosition(
      (position) => {
        setFix({ at: [position.coords.longitude, position.coords.latitude], flyTo: first ? why : null })
        first = false
      },
      (failure) => {
        setLocateError(failure.code === failure.PERMISSION_DENIED ? 'Location is off for this site.' : 'Your position could not be found.')
        if (watching.current !== null) navigator.geolocation.clearWatch(watching.current)
        watching.current = null
      },
      { enableHighAccuracy: true },
    )
  }
  const locateRef = useRef(locateOnBoard)
  locateRef.current = locateOnBoard
  useEffect(() => () => {
    if (watching.current !== null) navigator.geolocation.clearWatch(watching.current)
  }, [])
  const where = fix && board ? whereOnBoard(board, fix.at) : null
  useEffect(() => {
    const map = mapRef.current
    if (!map || !scoped) return
    const at = where && 'at' in where ? where.at : null
    const data: GeoJSONSourceSpecification['data'] = { type: 'FeatureCollection', features: at ? [{ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: at } }] : [] }
    const place = () => {
      const source = map.getSource('board-me') as GeoJSONSource | undefined
      if (source) return source.setData(data)
      if (!at) return
      map.addSource('board-me', { type: 'geojson', data })
      map.addLayer({ id: 'board-me-halo', type: 'circle', source: 'board-me', paint: { 'circle-radius': 16, 'circle-color': '#2F7CF6', 'circle-opacity': 0.18, 'circle-pitch-alignment': 'map' } })
      map.addLayer({ id: 'board-me', type: 'circle', source: 'board-me', paint: { 'circle-radius': 6.5, 'circle-color': '#2F7CF6', 'circle-stroke-color': '#FFFFFF', 'circle-stroke-width': 2.5 } })
    }
    try {
      place()
    } catch {
      map.once('idle', place) // the style is still coming in
    }
    if (!fix?.flyTo || !where || focusRef.current) return
    if (at) map.flyTo({ center: at, zoom: Math.max(map.getZoom(), 16), duration: flyMs(), essential: true })
    else if (fix.flyTo === 'tap' && 'nearest' in where) {
      const r = boardRect(where.nearest)
      map.fitBounds([worldAt([r.x0, r.y1]), worldAt([r.x1, r.y0])], { padding: fitPadding(), maxZoom: 16, duration: flyMs() })
    }
    setFix({ ...fix, flyTo: null }) // flown once; the dot keeps following
    // `where` follows `fix` and `board`; `dark`: a theme change drops the layers
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fix, board, dark, scoped])
  useEffect(() => {
    if (!('geolocation' in navigator) || focusId || locateAsked.current) return
    locateAsked.current = true
    let dismissed = false
    let allowed = false
    try {
      dismissed = localStorage.getItem(LOCATE_DISMISSED) === '1'
      allowed = localStorage.getItem(LOCATE_ALLOWED) === '1'
    } catch {
      // storage blocked: ask again next time
    }
    let cancelled = false
    let answered = false
    navigator.permissions
      ?.query({ name: 'geolocation' })
      .then((status) => {
        if (cancelled) return
        answered = true
        // allowed here before: straight to the browser's own prompt, not our card again in front of it
        if (status.state === 'granted' || (status.state === 'prompt' && allowed)) locate()
        else if (status.state === 'prompt' && !dismissed) setAskLocation(true)
      })
      .catch(() => {
        if (cancelled) return
        answered = true
        if (allowed) locate()
        else if (!dismissed) setAskLocation(true)
      })
    if (!navigator.permissions) {
      answered = true
      if (allowed) locate()
      else if (!dismissed) setAskLocation(true)
    }
    return () => {
      cancelled = true
      // undone before the browser answered (React's dev double mount, a building opened at once): the next run asks
      if (!answered) locateAsked.current = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusId])
  const answerLocation = (allow: boolean) => {
    setAskLocation(false)
    try {
      localStorage.setItem(allow ? LOCATE_ALLOWED : LOCATE_DISMISSED, '1')
    } catch {
      // storage blocked: nothing to remember
    }
    if (allow) locate()
  }

  // the picked building stays lit on the map (feature state is dropped with a style swap, so set again on style.load)
  useEffect(() => {
    const map = mapRef.current
    if (!map || !picked) return
    const light = () => selectBuilding(map, picked, true)
    light()
    map.on('style.load', light)
    map.on('idle', light)
    return () => {
      map.off('style.load', light)
      map.off('idle', light)
      if (mapRef.current === map) selectBuilding(map, picked, false) // (not once the map itself is gone)
    }
  }, [picked])

  // a row: a building on the map is flown to and picked (it opens from the map); one with no position has nowhere
  // to fly to, so it opens at once
  const pick = (b: Building) => {
    const map = mapRef.current
    if (!b.location || !map) return onOpen(b.id)
    setPicked(b.id)
    closeList() // the map flies to it; the closed card keeps it with Open
    const outline = (b.location.outline ?? []).flat()
    const bounds = new maplibregl.LngLatBounds()
    for (const point of outline.length ? outline : [[b.location.lon, b.location.lat] as [number, number]]) bounds.extend(point)
    const camera = map.cameraForBounds(bounds, { padding: fitPadding(), maxZoom: PICK_ZOOM })
    map.flyTo({ ...camera, zoom: Math.min(camera?.zoom ?? PICK_ZOOM, PICK_ZOOM), pitch: PITCH, duration: flyMs(), essential: true })
  }

  // a row under the pointer (or focus) enlarges its pin
  const mark = (id: string, on: boolean) => {
    const map = mapRef.current
    if (map) hoverBuilding(map, id, on)
  }

  return (
    <main
      className={`ml${focus ? ' ml-open' : ''}${listOpen ? ' ml-listing' : ''}`}
      inert={focus ? true : undefined}
      style={topHeight ? ({ '--ml-top': `${topHeight}px` } as CSSProperties) : undefined}
    >
      <div ref={container} className="ml-map" />
      {scoped && !focus && !arranging && !nearClosed && (locateError || (where && 'nearest' in where)) && (
        <p className="ml-near" role="status">
          <span>
            {locateError ?? (where && 'nearest' in where
              ? `You are not on this map. Nearest site: ${where.nearest.name ?? nameOfId(where.nearest.buildings[0])}, ${distanceLabel(where.metres)} away.`
              : '')}
          </span>
          <button type="button" aria-label="Close" onClick={() => setNearClosed(true)}>×</button>
        </p>
      )}
      {askLocation && !focus && (
        <div className="ml-locate-scrim" onKeyDown={(e) => e.key === 'Escape' && answerLocation(false)}>
          <div className="ml-locate" role="dialog" aria-modal="true" aria-labelledby="ml-locate-title">
            <span className="ml-locate-icon" aria-hidden>
              <svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 21s-7-6.2-7-11.5a7 7 0 0 1 14 0C19 14.8 12 21 12 21z" />
                <circle cx="12" cy="9.5" r="2.5" />
              </svg>
            </span>
            <p id="ml-locate-title">Show where you are?</p>
            <p className="ml-locate-sub">Your position appears as a dot among the buildings. It stays in this browser.</p>
            <div className="ml-locate-actions">
              <button className="ml-locate-allow" onClick={() => answerLocation(true)} autoFocus>
                Allow location
              </button>
              <button onClick={() => answerLocation(false)}>Not now</button>
            </div>
          </div>
        </div>
      )}
      {card && (
        <div
          className={`ml-create${cardXY?.below ? ' below' : ''}`} role="dialog" aria-labelledby="ml-create-title"
          style={cardXY && !narrow ? { left: cardXY.x, top: cardXY.y } : undefined}
          onKeyDown={(event) => event.key === 'Escape' && setCard(null)}
        >
          <div className="ml-create-head">
            <span className="ml-create-icon" aria-hidden>
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M4 20V9l8-5 8 5v11" />
                <path d="M9 20v-6h6v6" />
              </svg>
            </span>
            <div>
              <p id="ml-create-title" className="ml-create-title">
                {card.kind === 'ours'
                  ? card.ids.length > 1 ? 'Which version?' : nameOfId(card.ids[0])
                  : card.place.name ?? ('ring' in card.place ? 'This building' : 'This spot')}
              </p>
              <p className="ml-create-sub">
                {card.kind === 'ours'
                  ? card.ids.length > 1 ? `${card.ids.length} versions stand here.` : addressOf(card.ids[0]) ?? 'A building with its own model.'
                  : 'ring' in card.place ? 'Make a model of it from photos or PDFs of its floor plans.' : 'No building is mapped here. Place a new one on this spot from its floor plans.'}
              </p>
              {card.kind === 'ours' && card.ids.length === 1 && badgeOf(card.ids[0]) && (
                <OrgBadge badge={badgeOf(card.ids[0])!} onOpenMap={onOpenMap && ((slug) => {
                  setCard(null)
                  onOpenMap(slug)
                })} />
              )}
            </div>
          </div>
          {card.kind === 'ours' && card.ids.length > 1 && (
            <ol className="ml-create-versions">
              {card.ids.map((id) => (
                <li key={id}>
                  <button onClick={() => {
                    if (card.pick) return setCard({ ...card, ids: [id] }) // right click: act on this version
                    setCard(null)
                    onOpen(id)
                  }}>
                    <span className="ml-name">{nameOfId(id)}</span>
                    {(addressOf(id) || id.startsWith('user/')) && (
                      <span className="ml-address">{[versionOf(id), addressOf(id)].filter(Boolean).join(', ')}</span>
                    )}
                  </button>
                </li>
              ))}
            </ol>
          )}
          <div className="ml-create-actions">
            {card.kind === 'ours' ? (
              <>
                {card.ids.length === 1 && (
                  <button className="ml-create-main" autoFocus onClick={() => {
                    setCard(null)
                    onOpen(card.ids[0])
                  }}>
                    Open
                  </button>
                )}
                {canCreate && card.ids.length === 1 && card.ids[0].startsWith('user/') && (
                  <button className="ml-create-delete" disabled={deleting === 'busy'} onClick={async () => {
                    if (deleting !== 'ask') return setDeleting('ask')
                    setDeleting('busy')
                    try {
                      await api.deleteBuilding(card.ids[0])
                      setCard(null)
                      onDeleted()
                    } catch (reason) {
                      setDeleting(reason instanceof Error ? reason.message : String(reason))
                    }
                  }}>
                    {deleting === 'ask' ? `Delete ${nameOfId(card.ids[0])}? Click again` : deleting === 'busy' ? 'Deleting…' : 'Delete'}
                  </button>
                )}
                {deleting && deleting !== 'ask' && deleting !== 'busy' && <p className="ml-create-error">Not deleted: {deleting}</p>}
              </>
            ) : (
              <button className="ml-create-main" autoFocus onClick={() => {
                setCard(null)
                onImport(realPlace(card.place, card.at))
              }}>
                Create a building here
              </button>
            )}
            <button onClick={() => setCard(null)}>Cancel</button>
          </div>
        </div>
      )}
      {arranging && onArrange && board && !focus && (
        <div className="ml-arrange" role="toolbar" aria-label="Arrange the map">
          <p>{arrangeError ? `Not saved: ${arrangeError}` : 'Drag an island to move it, its edges to draw its area. Tap one to name it.'}</p>
          {board.byHand && (
            <button type="button" onClick={() => save({ sites: (layoutOf(board).sites ?? []).map((site) => ({ ...site, dx: null, dy: null })) })}>
              Line them up
            </button>
          )}
          <button type="button" className="ml-arrange-done" onClick={() => {
            setArranging(false)
            setNaming(null)
          }}>Done</button>
        </div>
      )}
      {naming && arranging && onArrange && board?.islands[naming.index] && (
        <form
          className="ml-create" role="dialog" aria-labelledby="ml-site-title"
          style={!narrow ? { left: naming.x, top: naming.y } : undefined}
          onKeyDown={(event) => event.key === 'Escape' && setNaming(null)}
          onSubmit={(event) => {
            event.preventDefault()
            save(layoutOf(changed(board, naming.index, { name: naming.name })))
            setNaming(null)
          }}
        >
          <p id="ml-site-title" className="ml-create-title">Name this site</p>
          <p className="ml-create-sub">{board.islands[naming.index].buildings.map(nameOfId).join(', ')}</p>
          <input className="ml-site-name" autoFocus maxLength={60} value={naming.name} placeholder="e.g. Garching"
            onChange={(event) => setNaming({ ...naming, name: event.target.value })} />
          <div className="ml-create-actions">
            <button type="submit" className="ml-create-main">Save name</button>
            {board.islands[naming.index].drawn && (
              <button type="button" disabled={overlaps(board, naming.index, boardRect(changed(board, naming.index, { fit: true }).islands[naming.index]))}
                title="Back to the area the app gives it: its buildings and 150 m round them" onClick={() => {
                  save(layoutOf(changed(board, naming.index, { fit: true })))
                  setNaming(null)
                }}>
                Fit the area to its buildings
              </button>
            )}
            <button type="button" onClick={() => setNaming(null)}>Cancel</button>
          </div>
        </form>
      )}
      {scope ? (
        <div className="ml-logo ml-scope">
          <h1>{scope.name}</h1>
          <p>
            {scope.org ? `${scope.org} · ` : ''}<button type="button" onClick={onLeaveScope}>{scope.org ? 'on Steward' : 'Back to the main map'}</button>
            {onArrange && board && !focus && !arranging && <> · <button type="button" onClick={() => setArranging(true)}>Arrange</button></>}
          </p>
        </div>
      ) : (
        <h1 className="ml-logo">
          <img src={dark ? '/brand/mark.svg' : '/brand/mark-light.svg'} alt="" />
          <Wordmark dark={dark} className="ml-wordmark" />
        </h1>
      )}
      <aside className={`ml-panel${listOpen ? ' open' : ''}`} onKeyDown={(e) => {
        if (e.key !== 'Escape') return
        if (query) setQuery('')
        else closeList()
      }}>
        <div className="ml-top" ref={top}>
          <label className="ml-field">
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden><circle cx="11" cy="11" r="6.5" /><path d="M16 16l4.5 4.5" /></svg>
            <input
              ref={input}
              value={query}
              onChange={(e) => {
                setQuery(e.target.value)
                setListOpen(true)
              }}
              onFocus={() => setListOpen(true)}
              onClick={() => setListOpen(true)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && shown[0]) pick(shown[0])
              }}
              placeholder={buildings ? `Search ${buildings.length} buildings` : error ? 'Could not load buildings' : 'Loading buildings…'}
              aria-label="Search buildings by name"
              aria-expanded={listOpen}
              aria-controls="ml-list"
              spellCheck={false}
              disabled={!buildings}
            />
            {/* typed: clear it; the list open and nothing typed: close the list */}
            {(query || listOpen) && (
              <button
                className="ml-clear"
                onClick={() => (query ? setQuery('') : closeList())}
                aria-label={query ? 'Clear search' : 'Close the list'}
              >
                <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden><path d="M6 6l12 12M18 6L6 18" /></svg>
              </button>
            )}
          </label>
          {!listOpen && picked && buildings?.some((b) => b.id === picked) && (
            <button className="ml-picked" onClick={() => onOpen(picked)}>
              <span className="ml-row-text">
                <span className="ml-name">{nameOfId(picked)}</span>
                {addressOf(picked) && <span className="ml-address">{addressOf(picked)}</span>}
              </span>
              {GO}
            </button>
          )}
          {!listOpen && pickedBadge && <OrgBadge badge={pickedBadge} onOpenMap={onOpenMap} />}
        </div>
        <div className="ml-body" id="ml-list" inert={listOpen ? undefined : true}>
          {kinds.length > 1 && (
            <div className="ml-kinds" role="group" aria-label="Filter by kind">
              {[{ kind: null, label: 'All' }, ...kinds].map((k) => (
                <button key={k.kind ?? 'all'} aria-pressed={kind === k.kind} onClick={() => setKind(k.kind)}>
                  {k.label}
                </button>
              ))}
            </div>
          )}
          <div className="ml-list">
            {[
              { key: 'map', label: 'On the map', items: shownLocated },
              { key: 'none', label: 'No location', items: shownElsewhere },
            ].map(
              (group) =>
                group.items.length > 0 && (
                  <section key={group.key}>
                    <h2>
                      <span>{group.label}</span>
                      <span>{group.items.length}</span>
                    </h2>
                    <ol>
                      {group.items.map((b, i) => (
                        <li key={b.id} className={picked === b.id ? 'on' : undefined} style={i < 12 ? ({ '--i': i } as CSSProperties) : undefined}>
                          <button
                            className="ml-row"
                            aria-current={picked === b.id || undefined}
                            onClick={() => (picked === b.id ? onOpen(b.id) : pick(b))}
                            onMouseEnter={() => mark(b.id, true)}
                            onMouseLeave={() => mark(b.id, false)}
                            onFocus={() => mark(b.id, true)}
                            onBlur={() => mark(b.id, false)}
                          >
                            <span className="ml-row-text">
                              <span className="ml-name">{nameOf(b)}</span>
                              {(b.location?.address || b.badge) && (
                                <span className="ml-address">
                                  {b.badge && <span className="ml-org">{b.badge.name}</span>}
                                  {b.location?.address}
                                </span>
                              )}
                            </span>
                            {picked === b.id && GO}
                          </button>
                        </li>
                      ))}
                    </ol>
                  </section>
                ),
            )}
            {buildings && !shown.length && (words.length > 0 || kind) && (
              <p className="ml-empty">
                {words.length ? `No ${kind ? `${KINDS.find((k) => k.kind === kind)!.label.toLowerCase()} building` : 'building'} is called “${query.trim()}”.` : 'No building of this kind.'}
              </p>
            )}
          </div>
          {canCreate && (
            <button className="ml-more" onClick={() => onImport()}>
              <span>New building from floor plans</span>
              <span aria-hidden>Create →</span>
            </button>
          )}
        </div>
      </aside>
    </main>
  )
}

/** An org's badge on the main map: its name; with a public map, a button that opens it. */
function OrgBadge({ badge, onOpenMap }: { badge: NonNullable<Building['badge']>; onOpenMap?: (slug: string) => void }) {
  const map = badge.map
  if (!map || !onOpenMap) return <p className="ml-badge"><span className="ml-org">{badge.name}</span></p>
  return (
    <button type="button" className="ml-badge" onClick={() => onOpenMap(map.slug)} title={`Open ${map.name}, ${badge.name}'s map`}>
      <span className="ml-org">{badge.name}</span>
      <span className="ml-badge-map">{map.name}</span>
      <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden><path d="M9 6l6 6-6 6" /></svg>
    </button>
  )
}

function pinBounds(located: Located[]) {
  if (!located.length) return null
  const bounds = new maplibregl.LngLatBounds()
  for (const b of located) bounds.extend([b.location.lon, b.location.lat])
  return bounds
}

const fitPadding = () => {
  const wide = innerWidth >= WIDE_PX
  return { ...FIT_PADDING, left: FIT_PADDING.left + (wide ? PANEL_PX : 0), bottom: FIT_PADDING.bottom + (wide ? 0 : 160) }
}
