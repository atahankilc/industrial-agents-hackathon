import { useEffect, useState } from 'react'
import { BuildingScreen } from './building/BuildingScreen.tsx'
import { MapLanding } from './map/MapLanding.tsx'
import { BuildingSearch } from './search/BuildingSearch.tsx'

// Landing is the map of the buildings that have a real position; the list view (?view=list) searches every
// building, including the ones without a position. Picking one opens its twin (?building=<split>/<id>); the pill at
// the top goes back to the map or the list, whichever it was opened from.

type Landing = 'map' | 'list'

const fromUrl = () => {
  const params = new URLSearchParams(location.search)
  const landing: Landing = params.get('view') === 'list' ? 'list' : 'map'
  return { building: params.get('building'), landing }
}

export function Root() {
  const [view, setView] = useState(fromUrl)

  useEffect(() => {
    const onPop = () => setView(fromUrl())
    addEventListener('popstate', onPop)
    return () => removeEventListener('popstate', onPop)
  }, [])

  const go = (building: string | null, landing: Landing) => {
    const params = new URLSearchParams(location.search)
    for (const key of ['go', 'view', 'building']) params.delete(key)
    if (landing === 'list') params.set('view', 'list')
    if (building) params.set('building', building)
    history.pushState(null, '', `${location.pathname}${params.size ? `?${params}` : ''}`)
    setView(fromUrl())
  }

  if (view.building)
    return (
      <BuildingScreen
        key={view.building}
        buildingId={view.building}
        onBack={() => go(null, view.landing)}
        onOpen={(id) => go(id, view.landing)}
      />
    )
  if (view.landing === 'list') return <BuildingSearch onOpen={(id) => go(id, 'list')} onMap={() => go(null, 'map')} />
  return <MapLanding onOpen={(id) => go(id, 'map')} onList={() => go(null, 'list')} />
}
