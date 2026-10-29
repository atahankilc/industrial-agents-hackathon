// node --experimental-strip-types frontend/scripts/board.check.ts — an organisation's island board (src/map/board.ts):
// sites from nearby buildings, islands edge to edge, moved by whole grid steps, seams with the real distance.
import assert from 'node:assert/strict'
import { arrange, boardOf, boardRect, boardShapes, changed, distanceLabel, dropAt, MAX_AREA_M, reshapeAt, islandAt, islandsOf, layoutOf, lngOf, latOf, metresBetween, onBoard, STEP, toBoard, toReal, worldX, worldY } from '../src/map/board.ts'

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

// an editor's layout: Garching dragged below the main campus, named; the stored board is the same on every screen
const all = [main, mensa, garching, freising]
const g = board.islands.findIndex((candidate) => candidate.buildings.includes('garching'))
const m = board.islands.findIndex((candidate) => candidate.buildings.includes('main'))
const home = boardRect(board.islands[m])
const size = boardRect(board.islands[g])
const below = { x0: home.x0 + 3 * STEP, y0: home.y1 + 5 * STEP, x1: home.x0 + 3 * STEP + size.x1 - size.x0, y1: home.y1 + 5 * STEP + size.y1 - size.y0 }
const dropped = dropAt(board, g, below, 10 * STEP)!
assert.equal(dropped.y0, home.y1) // pulled against the main campus's lower edge
assert.equal(dropped.x0, home.x0) // and its left edge
const arranged = changed(changed(board, g, { rect: dropped }), g, { name: '  Garching  ' })
assert.equal(arranged.islands[g].name, 'Garching')
assert.ok(arranged.seams.some((seam) => seam.anchor === 'right')) // a seam along the edge they now share
assert.equal(dropAt(board, g, home, 0), null) // onto another island: refused
const layout = layoutOf(arranged)
for (const arrangement of ['row', 'column'] as const) {
  const again = boardOf(all, arrangement, layout)!
  assert.equal(again.key, arranged.key)
  assert.deepEqual(again.islands.map(boardRect), arranged.islands.map(boardRect))
}
assert.ok(boardShapes(arranged).features.some((f) => f.properties.kind === 'island-name' && 'label' in f.properties && f.properties.label === 'Garching'))
// a building far away joins the map: its new island goes right of the stored board, the rest stay put
const tower = building('tower', 11.4600, 48.1800)
const grown = boardOf([...all, tower], 'row', layout)!
const right = Math.max(...arranged.islands.map((island) => boardRect(island).x1))
assert.equal(boardRect(grown.islands.find((island) => island.buildings.includes('tower'))!).x0, right)
assert.deepEqual(boardRect(grown.islands.find((island) => island.buildings.includes('garching'))!), dropped)
// names alone (nothing moved) keep the automatic arrangement
const named = boardOf(all, 'row', { sites: [{ buildings: ['freising'], name: 'Weihenstephan', dx: null, dy: null }] })!
assert.equal(named.key, row.key)
assert.ok(!named.byHand && arranged.byHand)
assert.equal(named.islands.find((island) => island.buildings.includes('freising'))!.name, 'Weihenstephan')

// a drawn area: Garching's right edge dragged out by 400 m and its top pulled in past its buildings
const gi = arranged.islands[g]
const now = boardRect(gi)
const metre = 1 / (2 * Math.PI * 6378137 * Math.cos((48.27 * Math.PI) / 180))
const wider = reshapeAt(arranged, g, { ...now, x1: now.x1 + 400 * metre }, { right: true }, 0)!
close(wider.x1 - now.x1, 400 * metre, STEP)
assert.equal(wider.x0, now.x0)
const tight = reshapeAt(arranged, g, { ...now, y0: now.y1 }, { top: true }, 0)!
assert.equal(tight.y0, gi.core.y0 + gi.dy) // stops at its buildings
const huge = reshapeAt(arranged, g, { ...now, x1: now.x1 + 9000 * metre }, { right: true }, 0)!
assert.ok((huge.x1 - huge.x0) / metre <= MAX_AREA_M + 1)
assert.equal(reshapeAt(arranged, g, { ...now, y0: now.y0 - 5000 * metre }, { top: true }, 0), null) // into the main campus
const drawn = changed(arranged, g, { area: wider })
assert.ok(drawn.islands[g].drawn)
assert.notEqual(drawn.key, arranged.key) // a new area is new tiles
assert.deepEqual(boardRect(drawn.islands[g]), wider) // drawn where it was dragged
const back = boardOf(all, 'row', layoutOf(drawn))!
assert.deepEqual(back.islands.map(boardRect), drawn.islands.map(boardRect)) // stored and found again
assert.ok(!changed(drawn, g, { fit: true }).islands[g].drawn)
// a drawn area too small for its site (a building added) grows back round the buildings
const small = layoutOf(drawn)
small.sites![g].area = { x0: small.sites![g].area!.x0 + 999999, y0: small.sites![g].area!.y0, x1: small.sites![g].area!.x0 + 999999 + 10, y1: small.sites![g].area!.y0 + 10 }
const grownBack = boardOf(all, 'row', small)!.islands.find((island) => island.buildings.includes('garching'))!
assert.ok(grownBack.real.x0 <= grownBack.core.x0 && grownBack.real.x1 >= grownBack.core.x1)

assert.equal(distanceLabel(842), '840 m')
assert.equal(distanceLabel(3420), '3.4 km')
assert.equal(distanceLabel(14600), '15 km')
console.log('board.check: ok')
