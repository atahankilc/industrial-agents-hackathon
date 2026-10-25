import { useEffect, useMemo, useState } from 'react'
import { AccessLayer } from './access/AccessLayer.tsx'
import { startAccess, useAccess } from './access/auth'
import { api, type Building } from './api'
import { BuildingScreen, type Showing } from './building/BuildingScreen.tsx'
import { prefetch } from './building/opening'
import { MapLanding } from './map/MapLanding.tsx'
import { BuildingSearch } from './search/BuildingSearch.tsx'
import { ImportScreen } from './import/ImportScreen.tsx'

// Landing is the map of the buildings that have a real position; the list view (?view=list) searches every
// building, including the ones without a position. Picking one opens its twin (?building=<split>/<id>); the pill at
// the top goes back to the map or the list, whichever it was opened from.
// A building with a position opens on top of the map, which stays mounted: the map flies in, then follows the
// model's camera. Two ways to look at it (remembered per browser): in its city, the neighbours on screen and their
// pins tappable; or alone, the map faded out behind it. Leaving fades the model out while the map flies back.

type Landing = 'map' | 'list' | 'import'

const LEAVE_MS = 350 // the building screen's fade-out (building/screen.css .screen.leaving)
const SHOWING_KEY = 'ttyb-building-showing'

startAccess() // GET /config; in access mode, the sign-in (src/access/auth.ts)

const fromUrl = () => {
  const params = new URLSearchParams(location.search)
  const view = params.get('view')
  const landing: Landing = view === 'list' || view === 'import' ? view : 'map'
  // ?edit=1: the building opens in the Edit mode (a building just created from floor plans)
  return { building: params.get('building'), landing, edit: params.get('edit') === '1' }
}

function storedShowing(): Showing {
  try {
    return localStorage.getItem(SHOWING_KEY) === 'alone' ? 'alone' : 'city'
  } catch {
    return 'city'
  }
}

export function Root() {
  const [view, setView] = useState(fromUrl)
  const [buildings, setBuildings] = useState<Building[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showing, setShowing] = useState(storedShowing)
  // the building on screen: it lags behind the URL while the one before fades out
  const [shown, setShown] = useState(view.building)
  // access mode: which buildings are listed depends on who is signed in
  const { version } = useAccess()

  useEffect(() => {
    api.buildings().then(setBuildings).catch((reason) => setError(String(reason)))
  }, [version])

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

  useEffect(() => {
    try {
      localStorage.setItem(SHOWING_KEY, showing)
    } catch {
      // storage unavailable: the choice just isn't remembered
    }
  }, [showing])

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

  const originOf = (id: string | null) => (id && buildings?.find((item) => item.id === id)?.location?.origin) || null
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
        <MapLanding buildings={buildings} error={error} focus={focus} onOpen={(id) => go(id, 'map')} onList={() => go(null, 'list')} onImport={() => go(null, 'import')} />
      )}
      {!view.building && !shown && view.landing === 'list' && (
        <BuildingSearch onOpen={(id) => go(id, 'list')} onMap={() => go(null, 'map')} onImport={() => go(null, 'import')} />
      )}
      {!view.building && !shown && view.landing === 'import' && (
        <ImportScreen onDone={(base) => go(base, 'list', true)} onExit={() => go(null, 'list')} />
      )}
      {shown && (
        <BuildingScreen
          key={shown}
          buildingId={shown}
          origin={withMap ? shownOrigin : null}
          showing={showing}
          onShowing={setShowing}
          leaving={leaving}
          startEditing={view.edit && view.building === shown}
          onBack={() => go(null, view.landing)}
          onOpen={(id) => go(id, view.landing)}
        />
      )}
      <AccessLayer />
    </>
  )
}
