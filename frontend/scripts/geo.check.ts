// node --experimental-strip-types frontend/scripts/geo.check.ts — building metres ↔ lat/lon with a bearing
// (src/map/geo.ts, the twin of backend/core/geoplace.py).
import assert from 'node:assert/strict'
import { fromLngLat, mapBearing, toLngLat, viewBearing } from '../src/map/geo.ts'

const R = 6378137
const deg = (r: number) => (r * 180) / Math.PI
const origin = { lat: 48.1497, lon: 11.5679 }
const close = (a: number, b: number, eps = 1e-9) => assert.ok(Math.abs(a - b) < eps, `${a} vs ${b}`)

// bearing 0 = the formula the app always used (x east, y north)
const [lng0, lat0] = toLngLat(origin, 10, 0)
close(lng0, origin.lon + deg(10 / (R * Math.cos((origin.lat * Math.PI) / 180))))
close(lat0, origin.lat)
// bearing 90: the building's x axis points north
const [lng1, lat1] = toLngLat({ ...origin, bearing: 90 }, 10, 0)
close(lng1, origin.lon)
close(lat1, origin.lat + deg(10 / R))
// round trip
const turned = { ...origin, bearing: 37 }
const [x, y] = fromLngLat(turned, ...toLngLat(turned, 12.5, -4.25))
close(x, 12.5, 1e-6)
close(y, -4.25, 1e-6)
// camera: a building turned 30° counter-clockwise looks 30° "left" of north on the map
close(mapBearing({ ...origin, bearing: 30 }, 0), -30)
close(viewBearing({ ...origin, bearing: 30 }, mapBearing({ ...origin, bearing: 30 }, 12)), 12)
console.log('geo.check: ok')

// a tile feature that merges several buildings: the part under the tap is the one, not the largest
import { outerRing } from '../src/map/geo.ts'
const square = (x: number, y: number, size: number) => [[x, y], [x + size, y], [x + size, y + size], [x, y + size], [x, y]]
const merged = { type: 'MultiPolygon', coordinates: [[square(0, 0, 10)], [square(20, 0, 2)]] }
assert.deepEqual(outerRing(merged, [21, 1])?.[0], [20, 0])
assert.deepEqual(outerRing(merged, [5, 5])?.[0], [0, 0])
assert.deepEqual(outerRing(merged, [19, 1])?.[0], [20, 0]) // outside every part: the nearest
console.log('geo.check (merged tiles): ok')
