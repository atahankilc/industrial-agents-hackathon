// node --experimental-strip-types frontend/scripts/board.check.ts — an organisation's island board (src/map/board.ts):
// sites from nearby buildings, islands edge to edge, moved by whole grid steps, seams with the real distance.
import assert from 'node:assert/strict'
import { arrange, boardOf, boardRect, distanceLabel, islandAt, islandsOf, lngOf, latOf, metresBetween, onBoard, STEP, toBoard, toReal, worldX, worldY } from '../src/map/board.ts'

const close = (a: number, b: number, eps = 1e-9) => assert.ok(Math.abs(a - b) < eps, `${a} vs ${b}`)
const square = (lng: number, lat: number, d = 0.0005): [number, number][] => [[lng - d, lat - d], [lng + d, lat - d], [lng + d, lat + d], [lng - d, lat + d], [lng - d, lat - d]]
const building = (id: string, lng: number, lat: number) => ({ id, location: { lat, lon: lng, origin: { lat, lon: lng }, outline: [square(lng, lat)] } })

// Mercator round trip
close(lngOf(worldX(11.57)), 11.57)
close(latOf(worldY(48.15)), 48.15)

// Stammgelände (two buildings 300 m apart: one site), Garching 15 km north, Weihenstephan further north
const main = building('main', 11.5680, 48.1490)
const mensa = building('mensa', 11.5720, 48.1495)
const garching = building('garching', 11.6700, 48.2650)
const freising = building('freising', 11.7230, 48.3990)
const sites = islandsOf([main, mensa, garching, freising].map((b) => ({ id: b.id, points: b.location.outline[0] })))
assert.equal(sites.length, 3)
assert.deepEqual(sites.find((site) => site.buildings.includes('main'))?.buildings.sort(), ['main', 'mensa'])
for (const site of sites) for (const value of Object.values(site.real)) assert.ok(value % STEP === 0) // on the grid

// a row: west to east, edge to edge, the first where it is, every move whole grid steps
const row = arrange(sites, 'row')
assert.deepEqual(row.islands.map((island) => island.buildings[0]), ['main', 'garching', 'freising'])
assert.equal(row.islands[0].dx, 0)
assert.equal(row.islands[0].dy, 0)
for (let i = 1; i < row.islands.length; i++) {
  assert.equal(boardRect(row.islands[i]).x0, boardRect(row.islands[i - 1]).x1) // no gap, no overlap
  assert.ok(row.islands[i].dx % STEP === 0)
  assert.ok(row.islands[i].dy % STEP === 0)
}
assert.equal(row.seams.length, 2)
assert.match(row.seams[0].label, /^1[45] km apart$/) // Stammgelände – Garching, about 15 km
assert.equal(row.seams[0].at, row.seams[0].line[1]) // under the seam's lower end
// a column: north to south
const column = arrange(sites, 'column')
assert.deepEqual(column.islands.map((island) => island.buildings[0]), ['freising', 'garching', 'main'])
assert.equal(boardRect(column.islands[1]).y0, boardRect(column.islands[0]).y1)
assert.equal(column.seams[0].anchor, 'right') // left of the seam
assert.notEqual(row.key, column.key)
assert.equal(arrange(sites, 'row').key, row.key) // the same board, the same key (its tiles are cached under it)

// moving a building keeps its size: its outline is as wide after as before (within Mercator's change of scale)
const board = boardOf([main, mensa, garching, freising], 'row')!
const moved = onBoard(board, garching)
const island = board.islands.find((candidate) => candidate.buildings.includes('garching'))!
const before = metresBetween(garching.location.outline[0][0], garching.location.outline[0][1])
const after = metresBetween(moved.location.outline[0][0], moved.location.outline[0][1])
assert.ok(Math.abs(after / before - 1) < 0.005, `${before} → ${after}`)
close(moved.location.origin.lon, moved.location.lon)
// and back: a point on the island is where it really is
const [lng, lat] = toReal(island, toBoard(island, [11.6701, 48.2651]))
close(lng, 11.6701, 1e-9)
close(lat, 48.2651, 1e-9)
assert.equal(islandAt(board, [moved.location.lon, moved.location.lat]), island)
assert.equal(islandAt(board, [0, 0]), null)
// one building alone: one island, no seams, not moved
const alone = boardOf([main], 'row')!
assert.equal(alone.seams.length, 0)
assert.deepEqual(onBoard(alone, main).location.outline, main.location.outline)
assert.equal(boardOf([{ id: 'x', location: null }], 'row'), null)

assert.equal(distanceLabel(842), '840 m')
assert.equal(distanceLabel(3420), '3.4 km')
assert.equal(distanceLabel(14600), '15 km')
console.log('board.check: ok')
