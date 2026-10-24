import { useEffect, useState } from 'react'
import { BuildingScreen } from './building/BuildingScreen.tsx'
import { BuildingSearch } from './search/BuildingSearch.tsx'

// Landing is the building search; picking one opens its twin (?building=<split>/<id>) and the pill at the top
// goes back.

const fromUrl = () => {
  const params = new URLSearchParams(location.search)
  return { building: params.get('building') }
}

export function Root() {
  const [view, setView] = useState(fromUrl)

  useEffect(() => {
    const onPop = () => setView(fromUrl())
    addEventListener('popstate', onPop)
    return () => removeEventListener('popstate', onPop)
  }, [])

  const open = (id: string | null) => {
    const params = new URLSearchParams(location.search)
    for (const key of ['go', 'view', 'building']) params.delete(key)
    if (id) params.set('building', id)
    history.pushState(null, '', `${location.pathname}${params.size ? `?${params}` : ''}`)
    setView(fromUrl())
  }

  if (view.building)
    return (
      <BuildingScreen key={view.building} buildingId={view.building} onBack={() => open(null)} />
    )
  return <BuildingSearch onOpen={open} />
}
