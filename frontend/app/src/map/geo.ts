// A building's metres ↔ lat/lon (the twin of core/geoplace.py): `origin` = lat/lon of the building's (0, 0),
// `bearing` = degrees counter-clockwise from east to the building's x axis (0 for every kit building: x east, y north).
// Local equirectangular projection, R = 6378137 m. Pure: no map, so `node --experimental-strip-types` can check it.

export type Origin = { lat: number; lon: number; bearing?: number }

const R = 6378137
const rad = (deg: number) => (deg * Math.PI) / 180
const deg = (r: number) => (r * 180) / Math.PI

export const toLngLat = (origin: Origin, x: number, y: number): [number, number] => {
  const b = rad(origin.bearing ?? 0)
  const east = x * Math.cos(b) - y * Math.sin(b)
  const north = x * Math.sin(b) + y * Math.cos(b)
  return [origin.lon + deg(east / (R * Math.cos(rad(origin.lat)))), origin.lat + deg(north / R)]
}

/** the inverse of toLngLat: a map point in the building's metres */
export const fromLngLat = (origin: Origin, lng: number, lat: number): [number, number] => {
  const east = rad(lng - origin.lon) * R * Math.cos(rad(origin.lat))
  const north = rad(lat - origin.lat) * R
  const b = rad(origin.bearing ?? 0)
  return [east * Math.cos(b) + north * Math.sin(b), -east * Math.sin(b) + north * Math.cos(b)]
}

/** A camera's turn in the building (degrees clockwise from the building's y axis) as MapLibre's bearing, and back. */
export const mapBearing = (origin: Origin, viewBearing: number) => viewBearing - (origin.bearing ?? 0)
export const viewBearing = (origin: Origin, mapBearingDeg: number) => mapBearingDeg + (origin.bearing ?? 0)

// the base map's OpenStreetMap buildings (src/map/style.ts), for "Create a building here" and placing an import
export const TILE_BUILDINGS = ['buildings-3d', 'buildings-3d-rest', 'footprint']

/** The outer ring ([lng, lat]) of a tapped base-map building. The tiles merge buildings of the same look into one
 * MultiPolygon, so the part that contains the tapped point `at` is taken (else the nearest part, else the largest). */
export const ringContains = (ring: number[][], [x, y]: [number, number]) => {
  let hit = false
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i]
    const [xj, yj] = ring[j]
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) hit = !hit
  }
  return hit
}

export function outerRing(geometry: { type: string; coordinates?: unknown }, at?: [number, number]): [number, number][] | null {
  const rings: number[][][] =
    geometry.type === 'Polygon' ? [(geometry.coordinates as number[][][])[0]]
      : geometry.type === 'MultiPolygon' ? (geometry.coordinates as number[][][][]).map((part) => part[0])
        : []
  const usable = rings.filter((ring) => ring && ring.length >= 4)
  if (!usable.length) return null
  const inside = (ring: number[][], [x, y]: [number, number]) => {
    let hit = false
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const [xi, yi] = ring[i]
      const [xj, yj] = ring[j]
      if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) hit = !hit
    }
    return hit
  }
  const nearest = (ring: number[][], [x, y]: [number, number]) => Math.min(...ring.map(([rx, ry]) => Math.hypot(rx - x, ry - y)))
  const area = (ring: number[][]) => Math.abs(ring.reduce((sum, [x, y], i) => {
    const [nx, ny] = ring[(i + 1) % ring.length]
    return sum + x * ny - nx * y
  }, 0))
  const ring = at
    ? usable.find((candidate) => inside(candidate, at)) ?? [...usable].sort((a, b) => nearest(a, at) - nearest(b, at))[0]
    : [...usable].sort((a, b) => area(b) - area(a))[0]
  return ring.map(([lng, lat]) => [lng, lat] as [number, number])
}
