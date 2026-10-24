// Landing: the buildings with a real position (GET /buildings `location`, the kit's OpenStreetMap buildings) as pins
// on a city map; tap a pin or a row to open the building. Every other building has no position and is found in the
// list view (search). Map: MapLibre with our own base style on OpenFreeMap's tiles (./style.ts), light or dark with
// the app theme, tilted, buildings extruded to their OSM height (streamed with the tiles, nothing stored). Pins and names are map layers drawn above, so names that would collide
// are dropped by the map itself.
// With a building open the map stays mounted under its screen (src/Root.tsx): it flies in to the building and then
// follows the model's camera (./bridge.ts), so in the city view the neighbours stay on screen and their pins can be
// tapped; shown alone, the building screen's own stage covers it. Closing the building flies back out to every pin.

import maplibregl, { type GeoJSONSource, type GeoJSONSourceSpecification, type Map as MapLibreMap } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { Building } from '../api'
import { useTheme } from '../theme'
import { applyBlocks, attachMap, FLAT_FOV, osmHeights, toLngLat, type Origin } from './bridge'
import './map.css'
import { BUILDINGS_FROM_ZOOM, mapStyle, modelColours } from './style'

const MUNICH = { center: [11.575, 48.14] as [number, number], zoom: 10.5 }
const FIT_PADDING = { top: 80, right: 60, bottom: 80, left: 60 }
const PANEL_PX = 340 // wide screens: the list panel covers the map's left edge
const WIDE_PX = 900
const PITCH = 50
const FOV = 36.87 // MapLibre's own vertical field of view (degrees)
const FLY = { zoom: 17.6, pitch: 56, bearing: -45 } // close to where the model's first framing lands (src/plan/PlanView.tsx TILTED)
const FLY_MS = 1500
const CALM_FLY_MS = 1000 // with "reduce motion" on: still a flight (the move tells you where you are), just shorter
const flyMs = () => (matchMedia('(prefers-reduced-motion: reduce)').matches ? CALM_FLY_MS : FLY_MS)
// pins in the HUD's ink, ringed in the ground colour, on a soft disc that marks them from afar (no glow)
const PIN = {
  light: { fill: '#111215', ring: '#F2F2EF', disc: '#111215', text: '#111215', halo: '#F2F2EF' },
  dark: { fill: '#F3F4F6', ring: '#0F1013', disc: '#F3F4F6', text: '#F3F4F6', halo: '#0F1013' },
}

const LOCATE_DISMISSED = 'ml-locate-dismissed' // "Not now" on the location card, remembered per browser

type Located = Building & { location: NonNullable<Building['location']> }
const nameOf = (b: Building) => b.name ?? b.id.split('/')[1]
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

export function MapLanding({ buildings, error, focus, onOpen, onList }: {
  buildings: Building[] | null
  error: string | null
  focus: Focus | null
  onOpen: (id: string) => void
  onList: () => void
}) {
  const { dark } = useTheme()
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const openRef = useRef(onOpen)
  openRef.current = onOpen
  const focusRef = useRef(focus)
  focusRef.current = focus
  const geolocateRef = useRef<maplibregl.GeolocateControl | null>(null)
  const [askLocation, setAskLocation] = useState(false)

  const located = useMemo(
    () =>
      (buildings ?? [])
        .filter((b): b is Located => Boolean(b.location))
        .sort((a, b) => nameOf(a).localeCompare(nameOf(b), undefined, { numeric: true })),
    [buildings],
  )
  const elsewhere = (buildings?.length ?? 0) - located.length

  // the map: created once; its style follows the theme (a style swap drops our layers, so they go back on style.load)
  useEffect(() => {
    const map = new maplibregl.Map({
      container: container.current!,
      style: mapStyle(dark),
      ...MUNICH,
      pitch: PITCH,
      maxPitch: 75, // the model tilts to 69° (src/plan/PlanView.tsx MAX_POLAR)
      attributionControl: { compact: true },
    })
    // zoom about twice MapLibre's default speed (wheel 1/450, trackpad 1/100)
    map.scrollZoom.setWheelZoomRate(1 / 220)
    map.scrollZoom.setZoomRate(1 / 50)
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'bottom-right')
    // the viewer's own position as a dot (the browser asks first; it needs https or localhost)
    const geolocate = new maplibregl.GeolocateControl({ positionOptions: { enableHighAccuracy: true }, trackUserLocation: true, fitBoundsOptions: { maxZoom: 16 } })
    map.addControl(geolocate, 'bottom-right')
    geolocateRef.current = geolocate
    const open = (event: maplibregl.MapLayerMouseEvent) => {
      const id = event.features?.[0]?.properties?.id
      if (typeof id === 'string') openRef.current(id)
    }
    for (const layer of ['pins', 'pin-names']) {
      map.on('click', layer, open)
      map.on('mouseenter', layer, () => (map.getCanvas().style.cursor = 'pointer'))
      map.on('mouseleave', layer, () => (map.getCanvas().style.cursor = ''))
    }
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
        properties: { id: b.id, name: nameOf(b) },
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
      const models = modelColours(dark)
      const tall: maplibregl.ExpressionSpecification = ['+', ['max', ['get', 'height'], ['get', 'osm']], 0.4]
      map.addSource('models', { type: 'geojson', data: modelData() })
      map.addLayer({ id: 'model-footprints', type: 'fill', source: 'models', minzoom: 12, maxzoom: BUILDINGS_FROM_ZOOM + 0.6, paint: { 'fill-color': models.wall } })
      map.addLayer({
        id: 'model-blocks',
        type: 'fill-extrusion',
        source: 'models',
        minzoom: BUILDINGS_FROM_ZOOM,
        paint: {
          'fill-extrusion-color': ['interpolate', ['linear'], tall, 0, models.wall, 45, models.roof],
          'fill-extrusion-height': ['interpolate', ['linear'], ['zoom'], BUILDINGS_FROM_ZOOM, 0, BUILDINGS_FROM_ZOOM + 0.6, tall],
          'fill-extrusion-opacity': 0.95,
          'fill-extrusion-vertical-gradient': true,
        },
      })
      map.addSource('buildings', { type: 'geojson', data, promoteId: 'id' })
      const hover: maplibregl.ExpressionSpecification = ['boolean', ['feature-state', 'hover'], false]
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
          'text-field': ['get', 'name'],
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
    const modelData = (): GeoJSONSourceSpecification['data'] => {
      const osm = osmHeights(located.map((b) => b.location.outline ?? []))
      heights.key = osm.join(',')
      return {
        type: 'FeatureCollection',
        features: located.map((b, i) => ({
          type: 'Feature',
          properties: { id: b.id, height: b.location.height_m ?? 0, osm: osm[i] ?? 0 },
          geometry: { type: 'MultiPolygon', coordinates: (b.location.outline ?? []).map((ring) => [ring]) },
        })),
      }
    }
    const updateHeights = () => {
      const source = modelsSource()
      if (!source) return
      const key = osmHeights(located.map((b) => b.location.outline ?? [])).join(',')
      if (key !== heights.key) source.setData(modelData())
    }
    tryPins()
    map.on('idle', updateHeights)
    map.on('style.load', addPins)
    map.on('style.load', hideFocused)
    map.on('style.load', applyBlocks)
    return () => {
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
    for (const layer of ['pin-discs', 'pins', 'pin-names', 'model-footprints', 'model-blocks']) if (map.getLayer(layer)) map.setFilter(layer, pinFilter)
  }

  // fly in to the open building (or jump, if the map just appeared under it), flattening the perspective so the
  // model's camera can take over; fly back out to every pin when it closes
  const focusId = focus?.id ?? null
  const flownTo = useRef<string | null>(null)
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    const was = flownTo.current
    flownTo.current = focusId
    const current = focusRef.current
    if (current) {
      const first = !was && !map.loaded() && !framed.current
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
    const bounds = pinBounds(located)
    const ms = flyMs()
    if (bounds) {
      const camera = map.cameraForBounds(bounds, { padding: fitPadding(), maxZoom: 15 })
      if (camera) map.flyTo({ ...camera, pitch: PITCH, bearing: 0, duration: ms, essential: true })
    }
    easeFov(map, FOV, ms)
    hideFocused()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusId])

  // theme change: swap the base style (pins are re-added on style.load above)
  const shownStyle = useRef(dark)
  useEffect(() => {
    const map = mapRef.current
    if (!map || shownStyle.current === dark) return
    shownStyle.current = dark
    map.setStyle(mapStyle(dark), { diff: false })
  }, [dark])

  // frame every pin once they are known, clear of the list panel on wide screens (not while a building is open)
  const framed = useRef(false)
  useEffect(() => {
    const map = mapRef.current
    const bounds = pinBounds(located)
    if (!map || framed.current || !bounds) return
    framed.current = true
    map.fitBounds(bounds, { pitch: PITCH, padding: fitPadding(), maxZoom: 15, duration: 0 })
  }, [located])

  // location on open: already allowed → show it; not asked yet → our card first, so a "no" is ours to take and the
  // browser's own prompt (which can stick as a denial) only follows a tap on Allow; denied → stay quiet
  const locate = () => {
    const map = mapRef.current
    const geolocate = geolocateRef.current
    if (!map || !geolocate) return
    if (map.loaded()) geolocate.trigger()
    else map.once('load', () => geolocate.trigger())
  }
  useEffect(() => {
    if (!('geolocation' in navigator) || focusRef.current) return
    let dismissed = false
    try {
      dismissed = localStorage.getItem(LOCATE_DISMISSED) === '1'
    } catch {
      // storage blocked: ask again next time
    }
    let cancelled = false
    navigator.permissions
      ?.query({ name: 'geolocation' })
      .then((status) => {
        if (cancelled) return
        if (status.state === 'granted') locate()
        else if (status.state === 'prompt' && !dismissed) setAskLocation(true)
      })
      .catch(() => !cancelled && !dismissed && setAskLocation(true))
    if (!navigator.permissions && !dismissed) setAskLocation(true)
    return () => {
      cancelled = true
    }
  }, [])
  const answerLocation = (allow: boolean) => {
    setAskLocation(false)
    if (allow) return locate()
    try {
      localStorage.setItem(LOCATE_DISMISSED, '1')
    } catch {
      // storage blocked: nothing to remember
    }
  }

  // a row under the pointer (or focus) enlarges its pin
  const mark = (id: string, on: boolean) => {
    const map = mapRef.current
    if (map?.getSource('buildings')) map.setFeatureState({ source: 'buildings', id }, { hover: on })
  }

  return (
    <main className={`ml${focus ? ' ml-open' : ''}`} inert={focus ? true : undefined}>
      <div ref={container} className="ml-map" />
      {askLocation && !focus && (
        <div className="ml-locate" role="dialog" aria-labelledby="ml-locate-title">
          <p id="ml-locate-title">Show where you are?</p>
          <p className="ml-locate-sub">Your position appears as a dot among the buildings. It stays in this browser.</p>
          <div className="ml-locate-actions">
            <button onClick={() => answerLocation(false)}>Not now</button>
            <button className="ml-locate-allow" onClick={() => answerLocation(true)} autoFocus>
              Allow
            </button>
          </div>
        </div>
      )}
      <aside className="ml-panel">
        <header>
          <h1>Buildings</h1>
          <p>{buildings ? `${located.length} on the map` : error ? 'Could not load buildings' : 'Loading…'}</p>
        </header>
        {located.length > 0 && (
          <ol className="ml-list">
            {located.map((b) => (
              <li key={b.id}>
                <button
                  onClick={() => onOpen(b.id)}
                  onMouseEnter={() => mark(b.id, true)}
                  onMouseLeave={() => mark(b.id, false)}
                  onFocus={() => mark(b.id, true)}
                  onBlur={() => mark(b.id, false)}
                >
                  <span className="ml-name">{nameOf(b)}</span>
                  {b.location.address && <span className="ml-address">{b.location.address}</span>}
                </button>
              </li>
            ))}
          </ol>
        )}
        <button className="ml-more" onClick={onList} disabled={!buildings}>
          <span>{buildings ? `${elsewhere} more without a location` : 'More buildings'}</span>
          <span aria-hidden>Search →</span>
        </button>
      </aside>
    </main>
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
