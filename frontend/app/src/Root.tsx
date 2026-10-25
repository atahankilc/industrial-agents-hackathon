import { useEffect, useMemo, useState } from 'react'
import { AccessLayer } from './access/AccessLayer.tsx'
import { startAccess, useAccess } from './access/auth'
import { api, type Building, type ImportPlace } from './api'
import { BuildingScreen } from './building/BuildingScreen.tsx'
import { prefetch } from './building/opening'
import { MapLanding } from './map/MapLanding.tsx'
import { BuildingSearch } from './search/BuildingSearch.tsx'
import { ImportScreen } from './import/ImportScreen.tsx'

// Landing is the map of the buildings that have a real position, its panel listing every building (the ones without
// a position after them); the list view (?view=list) searches them by id and type too.
// Picking one opens its twin (?building=<split>/<id>); the pill at the top goes back to the map or the list,
// whichever it was opened from.
// A building with a position opens on top of the map, which stays mounted: the map flies in, then follows the
// model's camera, in its city: the neighbours on screen and their pins tappable. Leaving fades the model out while
// the map flies back.

type Landing = 'map' | 'list' | 'import'

const LEAVE_MS = 350 // the building screen's fade-out (building/screen.css .screen.leaving)

startAccess() // GET /config; in access mode, the sign-in (src/access/auth.ts)

const fromUrl = () => {
  const params = new URLSearchParams(location.search)
  const view = params.get('view')
  const landing: Landing = view === 'list' || view === 'import' ? view : 'map'
  // ?edit=1: the building opens in the Edit mode (a building just created from floor plans)
  return { building: params.get('building'), landing, edit: params.get('edit') === '1' }
}


export function Root() {
  const [view, setView] = useState(fromUrl)
  const [buildings, setBuildings] = useState<Building[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  // the building on screen: it lags behind the URL while the one before fades out
  const [shown, setShown] = useState(view.building)
  // access mode: which buildings are listed depends on who is signed in
  const { version } = useAccess()

  // where "Create a building here" was tapped on the map (null: an import started from the list, no place)
  const [place, setPlace] = useState<ImportPlace | null>(null)
  const [deleted, setDeleted] = useState(0) // a building was deleted on the map: list again

  // again whenever the screen changes: a building saved in Edit mode (with its place on the map) shows at once
  useEffect(() => {
    api.buildings().then(setBuildings).catch((reason) => setError(String(reason)))
  }, [version, view.building, view.landing, deleted])

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

  const go = (building: string | null, landing: Landing, edit = false) => {
    if (building) prefetch(building) // the session and plan load while the map flies in
    const params = new URLSearchParams(location.search)
    for (const key of ['go', 'view', 'building', 'edit']) params.delete(key)
    if (landing !== 'map') params.set('view', landing)
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
  const withMap = (!view.building && view.landing === 'map') || Boolean(target) || (leaving && Boolean(shownOrigin))

  return (
    <>
      {withMap && (
        <MapLanding buildings={buildings} error={error} focus={focus} onOpen={(id) => go(id, 'map')} onImport={(where) => {
          setPlace(where ?? null)
          go(null, 'import')
        }} onDeleted={() => setDeleted((n) => n + 1)} />
      )}
      {!view.building && !shown && view.landing === 'list' && (
        <BuildingSearch onOpen={(id) => go(id, 'list')} onMap={() => go(null, 'map')} onImport={() => {
          setPlace(null)
          go(null, 'import')
        }} />
      )}
      {!view.building && !shown && view.landing === 'import' && (
        <ImportScreen place={place} onDone={(base) => go(base, 'list', true)} onExit={() => go(null, place ? 'map' : 'list')} />
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
        />
      )}
      <AccessLayer landing={!shown} />
    </>
  )
}
