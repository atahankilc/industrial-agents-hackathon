import { useEffect, useMemo, useState } from 'react'
import { AccessLayer } from './access/AccessLayer.tsx'
import { startAccess, useAccess } from './access/auth'
import { api, type Building, type ImportPlace, type OrgMapView } from './api'
import { BuildingScreen } from './building/BuildingScreen.tsx'
import { prefetch } from './building/opening'
import { MapLanding } from './map/MapLanding.tsx'
import { ImportScreen } from './import/ImportScreen.tsx'
import { OrgScreen } from './org/OrgScreen.tsx'

// Landing is the map of the buildings that have a real position, its search listing every building (the ones without
// a position after them); ?view=import is the create-from-floor-plans screen, ?view=org&org=<slug> an organisation's
// settings. ?map=<slug> (&k=<key> for a link-shared one) makes the landing an organisation's map: only its buildings
// (docs/product/organizations.md); it stays on while buildings open and close.
// Picking one opens its twin (?building=<id>); the pill at the top goes back to the map.
// A building with a position opens on top of the map, which stays mounted: the map flies in, then follows the
// model's camera, in its city: the neighbours on screen and their pins tappable. Leaving fades the model out while
// the map flies back.

type Landing = 'map' | 'import' | 'org'

const LEAVE_MS = 350 // the building screen's fade-out (building/screen.css .screen.leaving)

startAccess() // GET /config; in access mode, the sign-in (src/access/auth.ts)

const fromUrl = () => {
  const params = new URLSearchParams(location.search)
  const view = params.get('view')
  const landing: Landing = view === 'import' || view === 'org' ? view : 'map' // (an old ?view=list link lands on the map)
  // ?edit=1: the building opens in the Edit mode (a building just created from floor plans)
  return { building: params.get('building'), landing, edit: params.get('edit') === '1', map: params.get('map'),
    key: params.get('k'), org: params.get('org') }
}


export function Root() {
  const [view, setView] = useState(fromUrl)
  const [buildings, setBuildings] = useState<Building[] | null>(null)
  const [scope, setScope] = useState<OrgMapView | null>(null) // the organisation's map (?map=), once loaded
  const [error, setError] = useState<string | null>(null)
  // the building on screen: it lags behind the URL while the one before fades out
  const [shown, setShown] = useState(view.building)
  // access mode: which buildings are listed depends on who is signed in
  const { version } = useAccess()

  // where "Create a building here" was tapped on the map (null: an import started from the search panel, no place)
  const [place, setPlace] = useState<ImportPlace | null>(null)
  const [deleted, setDeleted] = useState(0) // a building was deleted on the map: list again

  // again whenever the screen changes: a building saved in Edit mode (with its place on the map) shows at once
  useEffect(() => {
    if (!view.map) {
      api
        .buildings()
        .then((list) => {
          setScope(null)
          setError(null)
          setBuildings(list)
        })
        .catch((reason) => setError(String(reason)))
      return
    }
    api
      .map(view.map, view.key)
      .then((map) => {
        setScope(map)
        setError(null)
        setBuildings(map.buildings)
      })
      .catch((reason) => {
        setScope(null)
        setBuildings([])
        setError(String(reason).includes('404') ? 'This map is not open to you. Sign in, or ask for its new link.' : String(reason))
      })
  }, [version, view.building, view.landing, view.map, view.key, deleted])

  useEffect(() => {
    const onPop = () => setView(fromUrl())
    addEventListener('popstate', onPop)
    return () => removeEventListener('popstate', onPop)
  }, [])

  // nothing on screen: the building comes at once; else after the one before has faded out
  if (!shown && view.building) setShown(view.building)
  useEffect(() => {
    if (view.building === shown || !shown) return
    const timer = setTimeout(() => setShown(view.building), LEAVE_MS)
    return () => clearTimeout(timer)
  }, [view.building, shown])

  const go = (building: string | null, landing: Landing, edit = false, place: { map?: string | null; key?: string | null; org?: string | null } = {}) => {
    if (building) prefetch(building) // the session and plan load while the map flies in
    const params = new URLSearchParams(location.search)
    for (const key of ['go', 'view', 'building', 'edit', 'org']) params.delete(key)
    // the organisation's map stays unless asked otherwise (null: back to the main map)
    if (place.map !== undefined) {
      params.delete('map')
      params.delete('k')
      if (place.map) params.set('map', place.map)
      if (place.map && place.key) params.set('k', place.key)
    }
    if (landing !== 'map') params.set('view', landing)
    if (landing === 'org' && place.org) params.set('org', place.org)
    if (building) params.set('building', building)
    if (building && edit) params.set('edit', '1')
    history.pushState(null, '', `${location.pathname}${params.size ? `?${params}` : ''}`)
    setView(fromUrl())
  }

  const originOf = (id: string | null) => {
    const location = id ? buildings?.find((item) => item.id === id)?.location : null
    return location?.origin ? { ...location.origin, bearing: location.bearing ?? 0 } : null
  }
  const target = originOf(view.building)
  const focus = useMemo(
    () => (view.building && target ? { id: view.building, origin: target } : null),
    [view.building, target],
  )
  const shownOrigin = originOf(shown)
  const leaving = shown !== null && shown !== view.building
  // the map is there for the landing, and under any building that has a place on it
  const withMap = (!view.building && view.landing !== 'import') || Boolean(target) || (leaving && Boolean(shownOrigin))

  return (
    <>
      {withMap && (
        <MapLanding key={view.map ?? ''} buildings={buildings} error={error} focus={focus} onOpen={(id) => go(id, 'map')} onImport={(where) => {
          setPlace(where ?? null)
          go(null, 'import')
        }} onDeleted={() => setDeleted((n) => n + 1)}
        scope={!view.map ? null : scope ? { name: scope.name, org: scope.org.name, orgSlug: scope.org.slug, verified: scope.org.verified } : error ? { name: error, org: null } : null}
        onLeaveScope={() => go(null, 'map', false, { map: null })} />
      )}
      {!view.building && !shown && view.landing === 'org' && (
        <OrgScreen slug={view.org} onExit={() => go(null, 'map')} onOpenMap={(map, key) => go(null, 'map', false, { map, key })}
          onOpenOrg={(org) => go(null, 'org', false, { org })} />
      )}
      {!view.building && !shown && view.landing === 'import' && (
        <ImportScreen place={place} org={view.map ? scope?.org.slug ?? null : null} onDone={(base) => go(base, 'map', true)} onExit={() => go(null, 'map')} />
      )}
      {shown && (
        <BuildingScreen
          key={shown}
          buildingId={shown}
          origin={withMap ? shownOrigin : null}
          leaving={leaving}
          startEditing={view.edit && view.building === shown}
          onBack={() => go(null, view.landing)}
          onOpen={(id) => go(id, view.landing)}
          org={buildings?.find((item) => item.id === shown)?.org ?? null}
        />
      )}
      <AccessLayer landing={!shown} />
    </>
  )
}
