// The landing map's own base style, drawn from OpenFreeMap's OpenMapTiles vector tiles (free, no key). The hosted
// styles paint parks, water and roads in flat greys; here every layer is ours, in the Quiet HUD's palette: a cool
// near-black (or paper white) ground, greens and water as quiet tints, roads as a grey hierarchy by class, buildings
// as footprints that rise into 3D blocks (OSM `render_height`). Farmland stays ground colour, so the countryside
// reads calm instead of patchy. Labels use the tile server's Noto glyphs.

import type { ExpressionSpecification, FillExtrusionLayerSpecification, FilterSpecification, LayerSpecification, StyleSpecification } from 'maplibre-gl'

export const BUILDINGS_FROM_ZOOM = 14 // OpenMapTiles carries buildings from z14
export const BUILDINGS_3D_FILTER: FilterSpecification = ['!=', ['get', 'hide_3d'], true] // outlines split into parts draw as their parts

type Palette = {
  land: string
  urban: string
  park: string
  wood: string
  grass: string
  water: string
  waterLine: string
  casing: string
  minor: string
  mid: string
  major: string
  motorway: string
  motorwayCasing: string
  /** walkways (footways, paths, pedestrian streets) a shade off the ground, unpaved ones sandier; cycle paths a faint
   * tint; steps drawn as treads */
  walk: string
  walkUnpaved: string
  cycle: string
  steps: string
  rail: string
  footprint: string
  footprintLine: string
  wall: string
  roof: string
  /** blocks of the buildings that have a model in the app (drawn by MapLanding from their kit footprints) */
  ours: string
  oursRoof: string
  label: string
  labelMuted: string
  labelWater: string
  labelGreen: string
  halo: string
  fog: string
}

const PALETTE: Record<'light' | 'dark', Palette> = {
  dark: {
    land: '#0F1013',
    urban: '#131418',
    park: '#16291F',
    wood: '#14241B',
    grass: '#182B21',
    water: '#0E2134',
    waterLine: '#163049',
    casing: '#0F1013',
    minor: '#262931',
    mid: '#2E313A',
    major: '#393D48',
    motorway: '#474C59',
    motorwayCasing: '#16171B',
    walk: '#1E2026',
    walkUnpaved: '#221F1B',
    cycle: '#1B2326',
    steps: '#2C2F37',
    rail: '#2A2C33',
    footprint: '#16171C',
    footprintLine: '#1E2026',
    wall: '#15161B',
    roof: '#262830',
    ours: '#1F3A5C',
    oursRoof: '#3A6FA8',
    label: '#A2A6AE',
    labelMuted: '#6E727A',
    labelWater: '#4F7894',
    labelGreen: '#5E8C72',
    halo: '#0F1013',
    fog: '#0F1013',
  },
  // light: paper ground with a hint of warmth, clear greens and blues, white roads drawn by their grey casing, and
  // blocks lit from one side so their faces separate (the flat greys before read as fog)
  light: {
    land: '#F1F0EC',
    urban: '#EAE9E4',
    park: '#CFE6C6',
    wood: '#C6DEBD',
    grass: '#D6EACE',
    water: '#A9CDEB',
    waterLine: '#93BFE4',
    casing: '#D3D1CA',
    minor: '#FFFFFF',
    mid: '#FFFFFF',
    major: '#FFFFFF',
    motorway: '#FFFFFF',
    motorwayCasing: '#BDB9B0',
    walk: '#FAF9F6',
    walkUnpaved: '#E6DFD0',
    cycle: '#E6EDF0',
    steps: '#D3D0C8',
    rail: '#C2C0B9',
    footprint: '#E3E2DD',
    footprintLine: '#D6D4CE',
    wall: '#D9D7D1',
    roof: '#FBFBF9',
    ours: '#9FC2EC',
    oursRoof: '#D6E6F8',
    label: '#2E3136',
    labelMuted: '#73777F',
    labelWater: '#3F709A',
    labelGreen: '#4C7F57',
    halo: '#F1F0EC',
    fog: '#F1F0EC',
  },
}

const LINES: ExpressionSpecification = ['match', ['geometry-type'], ['LineString', 'MultiLineString'], true, false]
const AREAS: ExpressionSpecification = ['match', ['geometry-type'], ['Polygon', 'MultiPolygon'], true, false]
const POINTS: ExpressionSpecification = ['match', ['geometry-type'], ['Point', 'MultiPoint'], true, false]
const NAME: ExpressionSpecification = ['coalesce', ['get', 'name:latin'], ['get', 'name']]
const FONT = { regular: ['Noto Sans Regular'], bold: ['Noto Sans Bold'], italic: ['Noto Sans Italic'] }

// a line width that doubles roughly every zoom level from `from` up, starting at `start` px
const width = (from: number, start: number, at20: number): ExpressionSpecification => ['interpolate', ['exponential', 1.5], ['zoom'], from, start, 20, at20]
// Roads at their real width from street zoom up. The tiles carry no width (OpenMapTiles `transportation` has class,
// surface, oneway… but no width or lanes, checked 2026-10-25), so each class gets a typical carriageway width
// (UNVERIFIED estimates for Munich streets, metres). From z15 a metre is drawn as many pixels as it is on the map,
// so the streets line up with the buildings; below that the widths ease in from a thin line.
const ROAD_M: Record<string, number> = { motorway: 24, trunk: 22, primary: 18, secondary: 14, tertiary: 11, minor: 8, service: 5, track: 4, rail: 3, transit: 3 }
const CURB_M = 1.5 // the light theme's casing: the kerb either side, together
// pixels per metre at zoom 0 at the buildings' latitude (Munich, 48.1°: every building on the map is in Bavaria)
const PX_PER_M = 512 / (2 * Math.PI * 6378137 * Math.cos((48.1 * Math.PI) / 180))
const metres = (classes: string[], extra = 0): ExpressionSpecification =>
  ['+', ['match', ['get', 'class'], ...classes.flatMap((name) => [name, ROAD_M[name] ?? 6]), 6], extra] as unknown as ExpressionSpecification
/** a road's width: `start` px at `from`, its real width from z15 on (pixels per metre double every zoom level) */
const metric = (from: number, start: number, classes: string[], extra = 0): ExpressionSpecification => [
  'interpolate', ['exponential', 2], ['zoom'],
  ...(from < 15 ? [from, start] : []),
  15, ['*', metres(classes, extra), PX_PER_M * 2 ** 15],
  22, ['*', metres(classes, extra), PX_PER_M * 2 ** 22],
] as ExpressionSpecification
// walkways: a sidewalk or footway, a pedestrian street, a platform, a cycle path (UNVERIFIED typical widths, metres)
const WALK_M = { footway: 2.5, pedestrian: 4, platform: 3, cycleway: 2 }
/** a walkway's width: its real width from z15 on, as the roads (`metres` may be a per-feature expression) */
const walkWidth = (metres: number | ExpressionSpecification): ExpressionSpecification => [
  'interpolate', ['exponential', 2], ['zoom'],
  15, ['*', metres, PX_PER_M * 2 ** 15],
  22, ['*', metres, PX_PER_M * 2 ** 22],
] as unknown as ExpressionSpecification
const roadClass = (...classes: string[]): ExpressionSpecification => ['all', LINES, ['match', ['get', 'class'], classes, true, false], ['!=', ['get', 'brunnel'], 'tunnel']]

function layers(p: Palette, dark: boolean): LayerSpecification[] {
  const src = { source: 'openmaptiles' } as const
  const height: ExpressionSpecification = ['coalesce', ['get', 'render_height'], 6]
  const solid = {
    // taller blocks catch more light, so a skyline reads at a glance
    'fill-extrusion-color': ['interpolate', ['linear'], height, 0, p.wall, 45, p.roof],
    // grow out of the ground over the first zoom level they show at
    'fill-extrusion-height': ['interpolate', ['linear'], ['zoom'], BUILDINGS_FROM_ZOOM, 0, BUILDINGS_FROM_ZOOM + 0.6, height],
    'fill-extrusion-base': ['coalesce', ['get', 'render_min_height'], 0],
    'fill-extrusion-opacity': BLOCK_OPACITY,
    'fill-extrusion-vertical-gradient': true,
  } satisfies FillExtrusionLayerSpecification['paint']
  // `casing` / `start`: their width in px at `from`, before the real width takes over
  const road = (id: string, classes: string[], from: number, casing: number | null, start: number, colour: string, casingColour = p.casing): LayerSpecification[] => [
    ...(casing
      ? [{ id: `${id}-casing`, type: 'line', ...src, 'source-layer': 'transportation', minzoom: from, filter: roadClass(...classes), layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': casingColour, 'line-width': metric(from, casing, classes, CURB_M) } } satisfies LayerSpecification]
      : []),
    { id, type: 'line', ...src, 'source-layer': 'transportation', minzoom: from, filter: roadClass(...classes), layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': colour, 'line-width': metric(from, start, classes) } },
  ]
  return [
    { id: 'land', type: 'background', paint: { 'background-color': p.land } },
    { id: 'urban', type: 'fill', ...src, 'source-layer': 'landuse', filter: ['all', AREAS, ['match', ['get', 'class'], ['residential', 'suburb', 'neighbourhood', 'commercial', 'retail', 'industrial', 'railway', 'school', 'university', 'college', 'hospital'], true, false]], paint: { 'fill-color': p.urban, 'fill-opacity': ['interpolate', ['linear'], ['zoom'], 8, 0, 11, 1] } },
    // woods fade in with zoom: at city scale they are only a soft tint, not a patchwork
    { id: 'wood', type: 'fill', ...src, 'source-layer': 'landcover', filter: ['all', AREAS, ['==', ['get', 'class'], 'wood']], paint: { 'fill-color': p.wood, 'fill-opacity': ['interpolate', ['linear'], ['zoom'], 6, dark ? 0.5 : 0.25, 12, 1] } },
    { id: 'grass', type: 'fill', ...src, 'source-layer': 'landcover', filter: ['all', AREAS, ['==', ['get', 'class'], 'grass']], paint: { 'fill-color': p.grass, 'fill-opacity': ['interpolate', ['linear'], ['zoom'], 9, 0, 12, 1] } },
    { id: 'green-use', type: 'fill', ...src, 'source-layer': 'landuse', filter: ['all', AREAS, ['match', ['get', 'class'], ['cemetery', 'pitch', 'playground', 'garden', 'stadium'], true, false]], paint: { 'fill-color': p.grass } },
    { id: 'park', type: 'fill', ...src, 'source-layer': 'park', filter: AREAS, paint: { 'fill-color': p.park, 'fill-opacity': ['interpolate', ['linear'], ['zoom'], 6, 0.6, 10, 1] } },
    { id: 'water', type: 'fill', ...src, 'source-layer': 'water', filter: ['all', AREAS, ['!=', ['get', 'brunnel'], 'tunnel']], paint: { 'fill-color': p.water } },
    { id: 'waterway', type: 'line', ...src, 'source-layer': 'waterway', minzoom: 9, filter: ['all', LINES, ['!=', ['get', 'brunnel'], 'tunnel']], paint: { 'line-color': p.waterLine, 'line-width': width(9, 0.6, 8) } },
    { id: 'aeroway', type: 'line', ...src, 'source-layer': 'aeroway', minzoom: 11, filter: LINES, paint: { 'line-color': p.minor, 'line-width': width(11, 1, 40) } },
    { id: 'footprint', type: 'fill', ...src, 'source-layer': 'building', minzoom: 13, maxzoom: BUILDINGS_FROM_ZOOM + 0.6, paint: { 'fill-color': p.footprint, 'fill-outline-color': p.footprintLine } },

    // squares and pedestrian zones the tiles carry as areas, in the road colour
    { id: 'pedestrian-area', type: 'fill', ...src, 'source-layer': 'transportation', minzoom: 14, filter: ['all', AREAS, ['match', ['get', 'class'], ['path', 'pedestrian'], true, false]], paint: { 'fill-color': p.minor, 'fill-opacity': ['interpolate', ['linear'], ['zoom'], 14, 0, 15, 1] } },
    // walkways and cycle paths as calm solid lines at their width, steps as treads (indoor corridors left out)
    {
      id: 'walk',
      type: 'line',
      ...src,
      'source-layer': 'transportation',
      minzoom: 15,
      filter: ['all', roadClass('path', 'pedestrian'), ['match', ['get', 'subclass'], ['steps', 'cycleway', 'corridor'], false, true]],
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: {
        'line-color': ['match', ['get', 'surface'], 'unpaved', p.walkUnpaved, p.walk],
        'line-width': walkWidth(['match', ['get', 'subclass'], 'pedestrian', WALK_M.pedestrian, 'platform', WALK_M.platform, WALK_M.footway]),
        'line-opacity': ['interpolate', ['linear'], ['zoom'], 15, 0, 15.5, 1],
      },
    },
    {
      id: 'cycle',
      type: 'line',
      ...src,
      'source-layer': 'transportation',
      minzoom: 15,
      filter: ['all', roadClass('path'), ['==', ['get', 'subclass'], 'cycleway']],
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: { 'line-color': p.cycle, 'line-width': walkWidth(WALK_M.cycleway), 'line-opacity': ['interpolate', ['linear'], ['zoom'], 15, 0, 15.5, 1] },
    },
    {
      id: 'steps',
      type: 'line',
      ...src,
      'source-layer': 'transportation',
      minzoom: 16,
      filter: ['all', roadClass('path'), ['==', ['get', 'subclass'], 'steps']],
      // treads: dashes a fifth of the width long (the dash array is in line widths)
      paint: { 'line-color': p.steps, 'line-width': walkWidth(WALK_M.footway), 'line-dasharray': [0.2, 0.2] },
    },
    { id: 'rail', type: 'line', ...src, 'source-layer': 'transportation', minzoom: 11, filter: roadClass('rail', 'transit'), paint: { 'line-color': p.rail, 'line-width': metric(11, 0.8, ['rail', 'transit']) } },
    ...road('road-minor', ['minor', 'service', 'track'], 13, dark ? null : 1.6, 1.2, p.minor),
    ...road('road-mid', ['tertiary'], 11, dark ? null : 1.4, 1, p.mid),
    ...road('road-major', ['primary', 'secondary'], 8, dark ? null : 1.4, 0.5, p.major),
    ...road('road-motorway', ['motorway', 'trunk'], 5, 1.2, 0.6, p.motorway, p.motorwayCasing),
    { id: 'bridge-motorway', type: 'line', ...src, 'source-layer': 'transportation', minzoom: 12, filter: ['all', LINES, ['==', ['get', 'brunnel'], 'bridge'], ['match', ['get', 'class'], ['motorway', 'trunk', 'primary'], true, false]], layout: { 'line-cap': 'round' }, paint: { 'line-color': p.motorway, 'line-width': metric(12, 1.5, ['motorway', 'trunk', 'primary']) } },

    { id: 'buildings-3d', type: 'fill-extrusion', ...src, 'source-layer': 'building', minzoom: BUILDINGS_FROM_ZOOM, filter: BUILDINGS_3D_FILTER, paint: solid },
    // pieces of tile blocks put back (src/map/bridge.ts applyBlocks): the tiles merge blocks of the same look into one
    // feature, often hundreds of buildings across the city, and a filter can only hide a feature whole; when one
    // piece of it has to go (under the open building or a building with a model), the rest is drawn from here
    { id: 'buildings-3d-rest', type: 'fill-extrusion', source: 'rest', minzoom: BUILDINGS_FROM_ZOOM, paint: solid },

    { id: 'water-name', type: 'symbol', ...src, 'source-layer': 'water_name', minzoom: 10, layout: { 'text-field': NAME, 'text-font': FONT.italic, 'text-size': 12, 'symbol-placement': ['step', ['zoom'], 'point', 12, 'line'] as never, 'text-letter-spacing': 0.05 }, paint: { 'text-color': p.labelWater, 'text-halo-color': p.halo, 'text-halo-width': 1.2 } },
    { id: 'park-name', type: 'symbol', ...src, 'source-layer': 'park', minzoom: 13, filter: POINTS, layout: { 'text-field': NAME, 'text-font': FONT.italic, 'text-size': 11.5, 'text-max-width': 8 }, paint: { 'text-color': p.labelGreen, 'text-halo-color': p.halo, 'text-halo-width': 1.2 } },
    { id: 'road-name', type: 'symbol', ...src, 'source-layer': 'transportation_name', minzoom: 14, filter: ['all', LINES, ['match', ['get', 'class'], ['primary', 'secondary', 'tertiary', 'minor', 'trunk'], true, false]], layout: { 'text-field': NAME, 'text-font': FONT.regular, 'text-size': ['interpolate', ['linear'], ['zoom'], 14, 10, 18, 13], 'symbol-placement': 'line', 'text-letter-spacing': 0.03, 'text-rotation-alignment': 'map' }, paint: { 'text-color': p.labelMuted, 'text-halo-color': p.halo, 'text-halo-width': 1.4 } },
    { id: 'place-small', type: 'symbol', ...src, 'source-layer': 'place', minzoom: 11, filter: ['match', ['get', 'class'], ['suburb', 'neighbourhood', 'quarter', 'village', 'hamlet'], true, false], layout: { 'text-field': NAME, 'text-font': FONT.regular, 'text-size': ['interpolate', ['linear'], ['zoom'], 11, 10.5, 16, 13], 'text-transform': 'uppercase', 'text-letter-spacing': 0.12, 'text-max-width': 8 }, paint: { 'text-color': p.labelMuted, 'text-halo-color': p.halo, 'text-halo-width': 1.4 } },
    { id: 'place-town', type: 'symbol', ...src, 'source-layer': 'place', minzoom: 8, maxzoom: 14, filter: ['==', ['get', 'class'], 'town'], layout: { 'text-field': NAME, 'text-font': FONT.regular, 'text-size': ['interpolate', ['linear'], ['zoom'], 8, 11, 13, 14] }, paint: { 'text-color': p.label, 'text-halo-color': p.halo, 'text-halo-width': 1.4 } },
    { id: 'place-city', type: 'symbol', ...src, 'source-layer': 'place', maxzoom: 13, filter: ['==', ['get', 'class'], 'city'], layout: { 'text-field': NAME, 'text-font': FONT.bold, 'text-size': ['interpolate', ['linear'], ['zoom'], 5, 12, 12, 18], 'text-letter-spacing': 0.02 }, paint: { 'text-color': p.label, 'text-halo-color': p.halo, 'text-halo-width': 1.6 } },
  ]
}

/** the accent the buildings with a model are drawn in: walls at the ground, lighter towards the roof */
export const modelColours = (dark: boolean) => {
  const p = PALETTE[dark ? 'dark' : 'light']
  return { wall: p.ours, roof: p.oursRoof }
}

const BLOCK_OPACITY = 0.95
const LIGHT_POSITION: [number, number, number] = [1.2, 210, 40]
const lightIntensity = (dark: boolean) => (dark ? 0.45 : 0.42)
/** a #RRGGBB colour as sRGB 0..1 */
export const rgb = (colour: string): [number, number, number] => {
  const n = parseInt(colour.slice(1), 16)
  return [(n >> 16) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255]
}

/** How the map draws its blocks, for the ones drawn around an open building (src/map/neighbours.ts): the same
 * colours, light and opacity, so the two cannot be told apart. */
export const blockLook = (dark: boolean) => {
  const p = PALETTE[dark ? 'dark' : 'light']
  return { wall: p.wall, roof: p.roof, ours: p.ours, oursRoof: p.oursRoof, position: LIGHT_POSITION, intensity: lightIntensity(dark), opacity: BLOCK_OPACITY, ground: rgb(p.land) }
}

/** the map's ground colour (the model tints what lies under the ground with it) */
export const groundColour = (dark: boolean) => PALETTE[dark ? 'dark' : 'light'].land

export function mapStyle(dark: boolean): StyleSpecification {
  const p = PALETTE[dark ? 'dark' : 'light']
  return {
    version: 8,
    sources: {
      rest: { type: 'geojson', data: { type: 'FeatureCollection', features: [] }, promoteId: 'piece' },
      openmaptiles: { type: 'vector', url: 'https://tiles.openfreemap.org/planet', attribution: '<a href="https://openfreemap.org">OpenFreeMap</a> © <a href="https://www.openmaptiles.org/">OpenMapTiles</a> Data from <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' },
    },
    glyphs: 'https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf',
    // the far ground fades into the background colour when the map is tilted, so the horizon stays quiet
    sky: { 'sky-color': p.fog, 'horizon-color': p.fog, 'fog-color': p.fog, 'fog-ground-blend': 0.6, 'horizon-fog-blend': 0.8, 'sky-horizon-blend': 1, 'atmosphere-blend': 0 },
    light: { anchor: 'viewport', color: '#FFFFFF', intensity: lightIntensity(dark), position: LIGHT_POSITION },
    layers: layers(p, dark),
  }
}
