// node --experimental-strip-types frontend/app/scripts/trace.check.ts — the trace's SVG matrix puts image pixels at
// the building metres the import's transform says (EditLayer draws building metres as they are).
import assert from 'node:assert/strict'
import { adjustTrace, traceAt, traceMatrix } from '../src/edit/geometry.ts'

const svg = traceMatrix([[0.02, 0, 1], [0, -0.02, 8]])
const [a, b, c, d, e, f] = svg.replace(/^matrix\(|\)$/g, '').split(' ').map(Number)
const apply = (u: number, v: number) => [a * u + c * v + e, b * u + d * v + f]
assert.deepEqual(apply(0, 0), [1, 8])
assert.deepEqual(apply(100, 50).map((value) => Math.round(value * 1e9) / 1e9), [3, 7])
const rotated = traceMatrix([[0, -0.5, 2], [0.5, 0, 3]])
const [a2, b2, c2, d2, e2, f2] = rotated.replace(/^matrix\(|\)$/g, '').split(' ').map(Number)
assert.deepEqual([a2 * 10 + c2 * 0 + e2, b2 * 10 + d2 * 0 + f2], [2, 8])

// adjusting: a move shifts every pixel; a turn / scale keeps the centre where it was
const t = [[0.02, 0, 1], [0, -0.02, 8]]
const near = (p: number[], q: number[]) => assert.ok(Math.hypot(p[0] - q[0], p[1] - q[1]) < 1e-9, `${p} != ${q}`)
near(traceAt(adjustTrace(t, { dx: 3, dy: -1 }), 100, 50), [6, 6])
const centre = traceAt(t, 50, 50)
const turned = adjustTrace(t, { angle: Math.PI / 2, centre })
near(traceAt(turned, 50, 50), centre)
near(traceAt(turned, 100, 50), [centre[0], centre[1] + 1]) // +1 m east turns to +1 m north
const scaled = adjustTrace(t, { scale: 2, centre })
near(traceAt(scaled, 50, 50), centre)
near(traceAt(scaled, 100, 50), [centre[0] + 2, centre[1]])
console.log('trace.check: ok')
