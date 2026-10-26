// A new building on the map, before Edit mode (archive/hackathon/superpowers/specs/2026-10-25-plan-reference-and-location-design.md):
// the import fitted it onto the tapped OSM footprint (dashed); here it can be dragged, turned and scaled by hand,
// then "Looks right" stores the position (PUT /drafts/{id}/location: origin, bearing, scale relative to now).
import maplibregl, { type GeoJSONSource } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useEffect, useMemo, useRef, useState } from 'react'
import { api, type DraftState, type ImportSuggestion, type PlacedLocation } from '../api'
import { useTheme } from '../theme'
import { fromLngLat, outerRing, TILE_BUILDINGS, toLngLat } from './geo'
import { mapStyle } from './style'

type Props = {
  draftId: string
  location: PlacedLocation
  target: [number, number][] | null // the tapped OSM footprint, [lng, lat]
  locatedBy?: 'tap' | 'photos' | 'device' | null
  suggestion?: ImportSuggestion | null // the photos point at another building than the tapped one
  onDone: (state: DraftState) => void
  doneLabel?: string
  /** the rooms of the floor being edited, in the building's metres — drawn instead of the lowest floor's outline */
  shape?: [number, number][][] | null
}

type Pose = { lat: number; lon: number; bearing: number; scale: number }

export function Placement({ draftId, location: fitted, target: tapped, locatedBy, suggestion, onDone, doneLabel = 'Looks right — edit the building', shape }: Props) {
  // the import's fit, or the "did you mean" building's once the user takes it
  const [location, setLocation] = useState(fitted)
  const [target, setTarget] = useState(tapped)
  const [offer, setOffer] = useState(suggestion ?? null)
  const { dark } = useTheme()
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const [pose, setPose] = useState<Pose>({ ...fitted.origin, bearing: fitted.bearing, scale: 1 })
  const poseRef = useRef(pose)
  poseRef.current = pose
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // the footprint in the building's metres (as fitted), so moving / turning / scaling redraws it exactly
  const metres = useMemo(() => {
    const start = { ...location.origin, bearing: location.bearing }
    return location.outline.map((ring) => ring.map(([lng, lat]) => fromLngLat(start, lng, lat)))
  }, [location])
  // one polygon per ring (a floor's rooms, or the outline): MultiPolygon coordinates
  const outline = (p: Pose) => (shape ?? metres).map((ring) => [ring.map(([x, y]) => toLngLat({ lat: p.lat, lon: p.lon, bearing: p.bearing }, x * p.scale, y * p.scale))])

  useEffect(() => {
    const map = new maplibregl.Map({
      container: container.current!,
      style: mapStyle(dark),
      center: [location.lon, location.lat],
      zoom: 18.2,
      attributionControl: { compact: true },
    })
    mapRef.current = map
    let drag: { from: maplibregl.LngLat; pose: Pose } | null = null
    map.on('load', () => {
      map.addSource('target', { type: 'geojson', data: { type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: target ? [target] : [] } } })
      map.addLayer({ id: 'target-line', type: 'line', source: 'target', paint: { 'line-color': '#6B7280', 'line-width': 2, 'line-dasharray': [2, 2] } })
      map.addSource('placed', { type: 'geojson', data: { type: 'Feature', properties: {}, geometry: { type: 'MultiPolygon', coordinates: outline(poseRef.current) } } })
      map.addLayer({ id: 'placed-fill', type: 'fill', source: 'placed', paint: { 'fill-color': '#2563EB', 'fill-opacity': 0.35 } })
      map.addLayer({ id: 'placed-line', type: 'line', source: 'placed', paint: { 'line-color': '#2563EB', 'line-width': 2.5 } })
      const begin = (event: maplibregl.MapLayerMouseEvent | maplibregl.MapLayerTouchEvent) => {
        event.preventDefault()
        drag = { from: event.lngLat, pose: poseRef.current }
        map.dragPan.disable()
      }
      map.on('mousedown', 'placed-fill', begin)
      map.on('touchstart', 'placed-fill', begin)
      map.on('mouseenter', 'placed-fill', () => (map.getCanvas().style.cursor = 'move'))
      map.on('mouseleave', 'placed-fill', () => (map.getCanvas().style.cursor = ''))
      // the backend found no OSM building (Overpass can be busy): the map's own building tiles say what stands there
      map.once('idle', () => void fromTiles(map))
    })
    const move = (event: maplibregl.MapMouseEvent | maplibregl.MapTouchEvent) => {
      if (!drag) return
      const { from, pose: start } = drag
      setPose({ ...start, lat: start.lat + event.lngLat.lat - from.lat, lon: start.lon + event.lngLat.lng - from.lng })
    }
    const end = () => {
      if (!drag) return
      drag = null
      map.dragPan.enable()
    }
    map.on('mousemove', move)
    map.on('touchmove', move)
    map.on('mouseup', end)
    map.on('touchend', end)
    return () => map.remove()
    // the map is made once per placement; the pose is drawn by the effect below
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const map = mapRef.current
    const placed = map?.getSource('placed') as GeoJSONSource | undefined
    placed?.setData({ type: 'Feature', properties: {}, geometry: { type: 'MultiPolygon', coordinates: outline(pose) } })
    const shown = map?.getSource('target') as GeoJSONSource | undefined
    shown?.setData({ type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: target ? [target] : [] } })
  })

  /** The base map's building at a point ({ring, name}), from the rendered tiles; null on open ground. */
  const tileBuildingAt = (map: maplibregl.Map, point: [number, number]) => {
    const layers = TILE_BUILDINGS.filter((layer) => map.getLayer(layer))
    const feature = layers.length ? map.queryRenderedFeatures(map.project(point), { layers })[0] : undefined
    const ring = feature ? outerRing(feature.geometry as { type: string; coordinates?: unknown }, point) : null
    return ring ? { ring, name: typeof feature?.properties?.name === 'string' ? (feature.properties.name as string) : null } : null
  }

  const fromTiles = async (map: maplibregl.Map) => {
    if (suggestion?.point && !suggestion.ring) {
      const there = tileBuildingAt(map, suggestion.point)
      if (there) setOffer({ ...there })
    }
    if ((locatedBy === 'photos' || locatedBy === 'device') && fitted.fit === null) {
      const here = tileBuildingAt(map, [fitted.lon, fitted.lat])
      if (!here) return
      try {
        const state = await api.fitDraft(draftId, here.ring, here.name)
        const next = (state.building.building as { location?: PlacedLocation }).location
        if (next) {
          setLocation(next)
          setPose({ ...next.origin, bearing: next.bearing, scale: 1 })
          setTarget(here.ring)
          setFittedTo(here.name ?? 'the building there')
        }
      } catch {
        // the point placement stands; the user can still move it by hand
      }
    }
  }
  const [fittedTo, setFittedTo] = useState<string | null>(null)

  const takeSuggestion = async () => {
    if (!offer) return
    setBusy(true)
    setError(null)
    try {
      if (offer.ring) {
        const state = await api.fitDraft(draftId, offer.ring, offer.name)
        const next = (state.building.building as { location?: PlacedLocation }).location
        if (next) {
          setLocation(next)
          setPose({ ...next.origin, bearing: next.bearing, scale: 1 })
          mapRef.current?.flyTo({ center: [next.lon, next.lat] })
        }
        setTarget(offer.ring)
      } else if (offer.point) {
        // no OSM building there: move the building's centre onto the photos' position
        const [lng, lat] = offer.point
        setPose((current) => ({ ...current, lat: current.lat + lat - location.lat, lon: current.lon + lng - location.lon }))
        mapRef.current?.flyTo({ center: offer.point })
        setTarget(null)
      }
      setOffer(null)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setBusy(false)
    }
  }

  const confirm = async () => {
    setBusy(true)
    setError(null)
    try {
      onDone(await api.setDraftLocation(draftId, { origin: { lat: pose.lat, lon: pose.lon }, bearing_deg: pose.bearing, scale: pose.scale }))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
      setBusy(false)
    }
  }

  const turn = (bearing: number) => setPose((current) => ({ ...current, bearing: ((bearing % 360) + 540) % 360 - 180 }))
  return (
    <section className="im-place-step" aria-label="Place the building on the map">
      {offer && (
        <div className="im-suggest" role="status">
          <p>These photos were taken {offer.name ? <>at <strong>{offer.name}</strong></> : 'somewhere else'}, not at the building you tapped. Did you mean that one?</p>
          <div>
            <button type="button" className="im-suggest-take" disabled={busy} onClick={takeSuggestion}>
              {offer.name ? `Use ${offer.name}` : 'Move it there'}
            </button>
            <button type="button" onClick={() => setOffer(null)}>Keep the tapped building</button>
          </div>
        </div>
      )}
      {locatedBy === 'photos' && <p className="im-located">Placed where the photos were taken{fittedTo ? `, onto ${fittedTo}` : ''}.</p>}
      {locatedBy === 'device' && <p className="im-located">Placed at your current position (the photos carry none){fittedTo ? `, onto ${fittedTo}` : ''}.</p>}
      <p>
        The building is laid onto the map{target ? ' over the building you tapped (dashed)' : ''}. Drag it to move it; turn
        and scale it below until it lines up.
        {location.fit?.low_confidence && <strong> The automatic fit was unsure — please check it.</strong>}
      </p>
      <div ref={container} className="im-place-map" />
      <div className="im-place-controls">
        <label>
          Turn {Math.round(pose.bearing)}°
          <input type="range" min={-180} max={180} step={0.5} value={pose.bearing > 180 ? pose.bearing - 360 : pose.bearing}
            onChange={(event) => turn(Number(event.target.value))} />
        </label>
        <button type="button" onClick={() => turn(pose.bearing - 1)} aria-label="Turn 1 degree clockwise">↻ 1°</button>
        <button type="button" onClick={() => turn(pose.bearing + 1)} aria-label="Turn 1 degree counter-clockwise">↺ 1°</button>
        <label>
          Size ×{pose.scale.toFixed(2)}
          <input type="range" min={0.75} max={1.25} step={0.01} value={pose.scale}
            onChange={(event) => setPose((current) => ({ ...current, scale: Number(event.target.value) }))} />
        </label>
      </div>
      {error && <p className="im-end">Could not save the position: {error}</p>}
      <button className="im-go" disabled={busy} onClick={confirm}>{busy ? 'Saving…' : doneLabel}</button>
    </section>
  )
}
