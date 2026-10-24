// The landing map's own base style, drawn from OpenFreeMap's OpenMapTiles vector tiles (free, no key). The hosted
// styles paint parks, water and roads in flat greys; here every layer is ours, in the Quiet HUD's palette: a cool
// near-black (or paper white) ground, greens and water as quiet tints, roads as a grey hierarchy by class, buildings
// as footprints that rise into 3D blocks (OSM `render_height`). Farmland stays ground colour, so the countryside
// reads calm instead of patchy. Labels use the tile server's Noto glyphs.

import type { ExpressionSpecification, LayerSpecification, StyleSpecification } from 'maplibre-gl'

export const BUILDINGS_FROM_ZOOM = 14 // OpenMapTiles carries buildings from z14

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
  path: string
  rail: string
  footprint: string
  footprintLine: string
  wall: string
  roof: string
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
    path: '#2A2D35',
    rail: '#2A2C33',
    footprint: '#16171C',
    footprintLine: '#1E2026',
    wall: '#15161B',
    roof: '#262830',
    label: '#A2A6AE',
    labelMuted: '#6E727A',
    labelWater: '#4F7894',
    labelGreen: '#5E8C72',
    halo: '#0F1013',
    fog: '#0F1013',
  },
  light: {
    land: '#F2F2EF',
    urban: '#ECECE8',
    park: '#DAE8D6',
    wood: '#D1E3CD',
    grass: '#DEEBDA',
    water: '#C6DBEA',
    waterLine: '#B3CFE3',
    casing: '#DCDCD6',
    minor: '#FFFFFF',
    mid: '#FFFFFF',
    major: '#FFFFFF',
    motorway: '#FFFFFF',
    motorwayCasing: '#C9C9C2',
    path: '#D6D6D0',
    rail: '#CFCFC9',
    footprint: '#E4E4DF',
    footprintLine: '#D8D8D2',
    wall: '#DCDCD6',
    roof: '#F4F4F1',
    label: '#3F4249',
    labelMuted: '#8D9199',
    labelWater: '#5A84A3',
    labelGreen: '#5D8A66',
    halo: '#F2F2EF',
    fog: '#F2F2EF',
  },
}

const LINES: ExpressionSpecification = ['match', ['geometry-type'], ['LineString', 'MultiLineString'], true, false]
const AREAS: ExpressionSpecification = ['match', ['geometry-type'], ['Polygon', 'MultiPolygon'], true, false]
const POINTS: ExpressionSpecification = ['match', ['geometry-type'], ['Point', 'MultiPoint'], true, false]
const NAME: ExpressionSpecification = ['coalesce', ['get', 'name:latin'], ['get', 'name']]
const FONT = { regular: ['Noto Sans Regular'], bold: ['Noto Sans Bold'], italic: ['Noto Sans Italic'] }

// a line width that doubles roughly every zoom level from `from` up, starting at `start` px
const width = (from: number, start: number, at20: number): ExpressionSpecification => ['interpolate', ['exponential', 1.5], ['zoom'], from, start, 20, at20]
const roadClass = (...classes: string[]): ExpressionSpecification => ['all', LINES, ['match', ['get', 'class'], classes, true, false], ['!=', ['get', 'brunnel'], 'tunnel']]

function layers(p: Palette, dark: boolean): LayerSpecification[] {
  const src = { source: 'openmaptiles' } as const
  const road = (id: string, classes: string[], from: number, casing: [number, number] | null, fill: [number, number], colour: string, casingColour = p.casing): LayerSpecification[] => [
    ...(casing
      ? [{ id: `${id}-casing`, type: 'line', ...src, 'source-layer': 'transportation', minzoom: from, filter: roadClass(...classes), layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': casingColour, 'line-width': width(from, casing[0], casing[1]) } } satisfies LayerSpecification]
      : []),
    { id, type: 'line', ...src, 'source-layer': 'transportation', minzoom: from, filter: roadClass(...classes), layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': colour, 'line-width': width(from, fill[0], fill[1]) } },
  ]
  return [
    { id: 'land', type: 'background', paint: { 'background-color': p.land } },
    { id: 'urban', type: 'fill', ...src, 'source-layer': 'landuse', filter: ['all', AREAS, ['match', ['get', 'class'], ['residential', 'suburb', 'neighbourhood', 'commercial', 'retail', 'industrial', 'railway', 'school', 'university', 'college', 'hospital'], true, false]], paint: { 'fill-color': p.urban, 'fill-opacity': ['interpolate', ['linear'], ['zoom'], 8, 0, 11, 1] } },
    { id: 'wood', type: 'fill', ...src, 'source-layer': 'landcover', filter: ['all', AREAS, ['==', ['get', 'class'], 'wood']], paint: { 'fill-color': p.wood, 'fill-opacity': ['interpolate', ['linear'], ['zoom'], 6, 0.5, 11, 1] } },
    { id: 'grass', type: 'fill', ...src, 'source-layer': 'landcover', filter: ['all', AREAS, ['==', ['get', 'class'], 'grass']], paint: { 'fill-color': p.grass, 'fill-opacity': ['interpolate', ['linear'], ['zoom'], 9, 0, 12, 1] } },
    { id: 'green-use', type: 'fill', ...src, 'source-layer': 'landuse', filter: ['all', AREAS, ['match', ['get', 'class'], ['cemetery', 'pitch', 'playground', 'garden', 'stadium'], true, false]], paint: { 'fill-color': p.grass } },
    { id: 'park', type: 'fill', ...src, 'source-layer': 'park', filter: AREAS, paint: { 'fill-color': p.park, 'fill-opacity': ['interpolate', ['linear'], ['zoom'], 6, 0.6, 10, 1] } },
    { id: 'water', type: 'fill', ...src, 'source-layer': 'water', filter: ['all', AREAS, ['!=', ['get', 'brunnel'], 'tunnel']], paint: { 'fill-color': p.water } },
    { id: 'waterway', type: 'line', ...src, 'source-layer': 'waterway', minzoom: 9, filter: ['all', LINES, ['!=', ['get', 'brunnel'], 'tunnel']], paint: { 'line-color': p.waterLine, 'line-width': width(9, 0.6, 8) } },
    { id: 'aeroway', type: 'line', ...src, 'source-layer': 'aeroway', minzoom: 11, filter: LINES, paint: { 'line-color': p.minor, 'line-width': width(11, 1, 40) } },
    { id: 'footprint', type: 'fill', ...src, 'source-layer': 'building', minzoom: 13, maxzoom: BUILDINGS_FROM_ZOOM + 0.6, paint: { 'fill-color': p.footprint, 'fill-outline-color': p.footprintLine } },

    { id: 'path', type: 'line', ...src, 'source-layer': 'transportation', minzoom: 15, filter: roadClass('path', 'pedestrian'), paint: { 'line-color': p.path, 'line-width': width(15, 0.8, 3), 'line-dasharray': [2, 1.5] } },
    { id: 'rail', type: 'line', ...src, 'source-layer': 'transportation', minzoom: 11, filter: roadClass('rail', 'transit'), paint: { 'line-color': p.rail, 'line-width': width(11, 0.8, 3) } },
    ...road('road-minor', ['minor', 'service', 'track'], 13, dark ? null : [1.6, 22], [1.2, 18], p.minor),
    ...road('road-mid', ['tertiary'], 11, dark ? null : [1.4, 26], [1, 22], p.mid),
    ...road('road-major', ['primary', 'secondary'], 8, dark ? null : [1.4, 30], [0.5, 26], p.major),
    ...road('road-motorway', ['motorway', 'trunk'], 5, [1.2, 36], [0.6, 30], p.motorway, p.motorwayCasing),
    { id: 'bridge-motorway', type: 'line', ...src, 'source-layer': 'transportation', minzoom: 12, filter: ['all', LINES, ['==', ['get', 'brunnel'], 'bridge'], ['match', ['get', 'class'], ['motorway', 'trunk', 'primary'], true, false]], layout: { 'line-cap': 'round' }, paint: { 'line-color': p.motorway, 'line-width': width(12, 1.5, 30) } },

    {
      id: 'buildings-3d',
      type: 'fill-extrusion',
      ...src,
      'source-layer': 'building',
      minzoom: BUILDINGS_FROM_ZOOM,
      filter: ['!=', ['get', 'hide_3d'], true],
      paint: {
        // taller blocks catch more light, so a skyline reads at a glance
        'fill-extrusion-color': ['interpolate', ['linear'], ['coalesce', ['get', 'render_height'], 6], 0, p.wall, 45, p.roof],
        // grow out of the ground over the first zoom level they show at
        'fill-extrusion-height': ['interpolate', ['linear'], ['zoom'], BUILDINGS_FROM_ZOOM, 0, BUILDINGS_FROM_ZOOM + 0.6, ['coalesce', ['get', 'render_height'], 6]],
        'fill-extrusion-base': ['coalesce', ['get', 'render_min_height'], 0],
        'fill-extrusion-opacity': 0.95,
        'fill-extrusion-vertical-gradient': true,
      },
    },

    { id: 'water-name', type: 'symbol', ...src, 'source-layer': 'water_name', minzoom: 10, layout: { 'text-field': NAME, 'text-font': FONT.italic, 'text-size': 12, 'symbol-placement': ['step', ['zoom'], 'point', 12, 'line'] as never, 'text-letter-spacing': 0.05 }, paint: { 'text-color': p.labelWater, 'text-halo-color': p.halo, 'text-halo-width': 1.2 } },
    { id: 'park-name', type: 'symbol', ...src, 'source-layer': 'park', minzoom: 13, filter: POINTS, layout: { 'text-field': NAME, 'text-font': FONT.italic, 'text-size': 11.5, 'text-max-width': 8 }, paint: { 'text-color': p.labelGreen, 'text-halo-color': p.halo, 'text-halo-width': 1.2 } },
    { id: 'road-name', type: 'symbol', ...src, 'source-layer': 'transportation_name', minzoom: 14, filter: ['all', LINES, ['match', ['get', 'class'], ['primary', 'secondary', 'tertiary', 'minor', 'trunk'], true, false]], layout: { 'text-field': NAME, 'text-font': FONT.regular, 'text-size': ['interpolate', ['linear'], ['zoom'], 14, 10, 18, 13], 'symbol-placement': 'line', 'text-letter-spacing': 0.03, 'text-rotation-alignment': 'map' }, paint: { 'text-color': p.labelMuted, 'text-halo-color': p.halo, 'text-halo-width': 1.4 } },
    { id: 'place-small', type: 'symbol', ...src, 'source-layer': 'place', minzoom: 11, filter: ['match', ['get', 'class'], ['suburb', 'neighbourhood', 'quarter', 'village', 'hamlet'], true, false], layout: { 'text-field': NAME, 'text-font': FONT.regular, 'text-size': ['interpolate', ['linear'], ['zoom'], 11, 10.5, 16, 13], 'text-transform': 'uppercase', 'text-letter-spacing': 0.12, 'text-max-width': 8 }, paint: { 'text-color': p.labelMuted, 'text-halo-color': p.halo, 'text-halo-width': 1.4 } },
    { id: 'place-town', type: 'symbol', ...src, 'source-layer': 'place', minzoom: 8, maxzoom: 14, filter: ['==', ['get', 'class'], 'town'], layout: { 'text-field': NAME, 'text-font': FONT.regular, 'text-size': ['interpolate', ['linear'], ['zoom'], 8, 11, 13, 14] }, paint: { 'text-color': p.label, 'text-halo-color': p.halo, 'text-halo-width': 1.4 } },
    { id: 'place-city', type: 'symbol', ...src, 'source-layer': 'place', maxzoom: 13, filter: ['==', ['get', 'class'], 'city'], layout: { 'text-field': NAME, 'text-font': FONT.bold, 'text-size': ['interpolate', ['linear'], ['zoom'], 5, 12, 12, 18], 'text-letter-spacing': 0.02 }, paint: { 'text-color': p.label, 'text-halo-color': p.halo, 'text-halo-width': 1.6 } },
  ]
}

export function mapStyle(dark: boolean): StyleSpecification {
  const p = PALETTE[dark ? 'dark' : 'light']
  return {
    version: 8,
    sources: { openmaptiles: { type: 'vector', url: 'https://tiles.openfreemap.org/planet', attribution: '<a href="https://openfreemap.org">OpenFreeMap</a> © <a href="https://www.openmaptiles.org/">OpenMapTiles</a> Data from <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' } },
    glyphs: 'https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf',
    // the far ground fades into the background colour when the map is tilted, so the horizon stays quiet
    sky: { 'sky-color': p.fog, 'horizon-color': p.fog, 'fog-color': p.fog, 'fog-ground-blend': 0.6, 'horizon-fog-blend': 0.8, 'sky-horizon-blend': 1, 'atmosphere-blend': 0 },
    light: { anchor: 'viewport', color: '#FFFFFF', intensity: dark ? 0.45 : 0.25, position: [1.2, 210, 40] },
    layers: layers(p, dark),
  }
}
