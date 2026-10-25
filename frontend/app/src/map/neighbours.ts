// The blocks around the open building, drawn by us inside the map (a MapLibre custom layer: the map's own GL context
// and depth, so the map's other blocks and its pins sort with them as before) instead of by the map, for one thing
// the map's own layers cannot do: an x-ray. Where a block stands between the camera and the building, the part of it
// over the building's outline on screen is cut away, its edge dissolving in a dither, and the rest of the block stays.
// Where a block is cut, its footprint shows on the ground (faint fill, outline), so you still see a building stands there.
// The cut follows the camera continuously; nothing switches on or off. The blocks are lit exactly as the map lights its
// own (MapLibre's fill-extrusion shader, reproduced below), so one drawn here looks the same as one drawn by the map.

import type { CustomLayerInterface, CustomRenderMethodInput, Map as MapLibreMap } from 'maplibre-gl'
import { ShapeUtils, Vector2 } from 'three'

/** A block: its polygon (outer ring, then holes; lng/lat), its base and top (metres), its colour (sRGB 0..1). */
export type Neighbour = { rings: [number, number][][]; base: number; top: number; colour: [number, number, number] }
/** The open building: its outline (any floor, metres east/north of `origin`) and its height above the ground. */
export type Focus = { origin: { lat: number; lon: number }; rings: [number, number][][]; height: number }
/** The map's light and the colour under the blocks (the map's blocks are 95% opaque over its ground). */
export type Look = { position: [number, number, number]; intensity: number; opacity: number; ground: [number, number, number] }

const R = 6378137 // the sphere src/map/bridge.ts measures metres on
const TILE_ZOOM = 14 // the tiles' own zoom (OpenMapTiles): a block crossing a tile edge comes clipped along it
const TILE_EDGE = 0.04 // tile buffer, as a share of the tile: a clipped edge lies within it of the tile's border
const XRAY_MARGIN = 1.1 // the cut reaches this far past the building's box on screen
const XRAY_SOFT = 0.35 // the share of the ellipse over which the cut dissolves into the block
const XRAY_DEPTH_M = 12 // a block's surface this far in front of the building's middle is cut fully; less, partly
const DITHER_CSS_PX = 2 // the dissolve's grain
const FADE_MS = 450 // the x-ray opening once the building is open

const VERTEX = `#version 300 es
#define FOOTPRINT 0.45
#define OUTLINE 0.9
uniform mat4 u_matrix;
uniform vec3 u_lightpos;
uniform float u_lightintensity;
uniform float u_opacity;
uniform vec3 u_ground;
in vec2 a_pos;
in vec3 a_normal;
in float a_t;
in float a_base;
in float a_height;
in vec3 a_color;
out vec4 v_color;
out float v_w;
out float v_kind;
void main() {
  // a_t: 0 at a wall's foot, 1 at its top and on the roof; 2 the footprint on the ground, 3 its outline
  v_kind = a_t > 2.5 ? 2.0 : a_t > 1.5 ? 1.0 : 0.0;
  float base = max(0.0, a_base);
  float height = max(0.0, a_height);
  float t = min(a_t, 1.0);
  gl_Position = u_matrix * vec4(a_pos, v_kind > 0.0 ? 0.0 : t > 0.0 ? height : base, 1.0);
  v_w = gl_Position.w;
  // MapLibre's fill-extrusion lighting (light colour white, vertical gradient on), normals in tile space (y south)
  vec3 color = a_color;
  float colorvalue = color.r * 0.2126 + color.g * 0.7152 + color.b * 0.0722;
  color += vec3(0.03);
  float directional = clamp(dot(a_normal, u_lightpos), 0.0, 1.0);
  directional = mix(1.0 - u_lightintensity, max(1.0 - colorvalue + u_lightintensity, 1.0), directional);
  if (a_normal.y != 0.0) directional *= clamp((t + base) * pow(height / 150.0, 0.5), mix(0.7, 0.98, 1.0 - u_lightintensity), 1.0);
  vec3 lit = clamp(color * directional, 0.0, 1.0);
  // the map composites its blocks at their opacity over the ground; drawn opaque here, over the ground colour. The
  // footprint is the roof's colour laid faintly on the ground, its outline a little stronger
  v_color = vec4(mix(u_ground, lit, v_kind == 0.0 ? u_opacity : v_kind == 1.0 ? FOOTPRINT : OUTLINE), 1.0);
}`

const FRAGMENT = `#version 300 es
precision highp float;
uniform vec2 u_centre;
uniform vec2 u_radius;
uniform float u_soft;
uniform float u_w;
uniform float u_depth;
uniform float u_grain;
uniform float u_strength;
in vec4 v_color;
in float v_w;
in float v_kind;
out vec4 fragColor;
float bayer(vec2 p) {
  vec2 q = mod(floor(p), 4.0);
  int i = int(q.x) + int(q.y) * 4;
  int m[16] = int[16](0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5);
  return (float(m[i]) + 0.5) / 16.0;
}
void main() {
  // inside the rounded box over the building (a superellipse, |x|⁴ + |y|⁴ = 1: it hugs the box and rounds its corners),
  // dissolving towards its rim; only what is in front
  vec2 d = abs((gl_FragCoord.xy - u_centre) / u_radius);
  d *= d;
  float inside = 1.0 - smoothstep(1.0 - u_soft, 1.0, sqrt(sqrt(dot(d, d))));
  float front = smoothstep(0.0, u_depth, u_w - v_w);
  bool cut = inside * front * u_strength > bayer(gl_FragCoord.xy / u_grain);
  // the block where it is not cut; its footprint on the ground exactly where it is, so you still see a building stood there
  if (cut == (v_kind == 0.0)) discard;
  fragColor = v_color;
}`

type Built = { buffer: WebGLBuffer; index: WebGLBuffer; count: number; lines: WebGLBuffer; lineCount: number }
const FLOATS = 2 + 3 + 1 + 1 + 1 + 3 // pos, normal, t, base, height, colour
// dev checks: the winding taken as front, and the x-ray on or off
const debug = { front: 'CCW' as 'CW' | 'CCW' | 'none', xray: true }
if (import.meta.env.DEV) Object.assign(window, { __xray: debug })

export function neighbourLayer(id: string, look: () => Look): CustomLayerInterface & {
  setBlocks: (focus: Focus | null, blocks: Neighbour[]) => void
} {
  let map: MapLibreMap | null = null
  let gl: WebGL2RenderingContext | null = null
  let program: WebGLProgram | null = null
  let built: Built | null = null
  let focus: Focus | null = null
  let pending: { focus: Focus | null; blocks: Neighbour[] } | null = null
  let openedAt = 0
  const where: Record<string, WebGLUniformLocation | null> = {}
  const attributes: Record<string, number> = {}

  const upload = () => {
    if (!gl || !pending) return
    focus = pending.focus
    const data = focus ? geometry(focus.origin, pending.blocks) : { vertices: new Float32Array(), indices: new Uint32Array(), lines: new Uint32Array() }
    pending = null
    if (built) for (const buffer of [built.buffer, built.index, built.lines]) gl.deleteBuffer(buffer)
    const buffer = gl.createBuffer()!
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer)
    gl.bufferData(gl.ARRAY_BUFFER, data.vertices, gl.STATIC_DRAW)
    const index = gl.createBuffer()!
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, index)
    gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, data.indices, gl.STATIC_DRAW)
    const lines = gl.createBuffer()!
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, lines)
    gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, data.lines, gl.STATIC_DRAW)
    built = { buffer, index, count: data.indices.length, lines, lineCount: data.lines.length }
  }

  return {
    id,
    type: 'custom',
    renderingMode: '3d',
    onAdd(next, context) {
      map = next
      gl = context as WebGL2RenderingContext
      program = link(gl, VERTEX, FRAGMENT)
      for (const name of ['u_matrix', 'u_lightpos', 'u_lightintensity', 'u_opacity', 'u_ground', 'u_centre', 'u_radius', 'u_soft', 'u_w', 'u_depth', 'u_grain', 'u_strength'])
        where[name] = gl.getUniformLocation(program, name)
      for (const name of ['a_pos', 'a_normal', 'a_t', 'a_base', 'a_height', 'a_color']) attributes[name] = gl.getAttribLocation(program, name)
      openedAt = performance.now()
      pending ??= { focus, blocks: [] }
    },
    onRemove() {
      if (gl && built) for (const buffer of [built.buffer, built.index, built.lines]) gl.deleteBuffer(buffer)
      if (gl && program) gl.deleteProgram(program)
      built = null
      program = null
      gl = null
      map = null
    },
    setBlocks(next, blocks) {
      if (next && next.origin !== focus?.origin) openedAt = performance.now()
      pending = { focus: next, blocks }
      map?.triggerRepaint()
    },
    render(context, args: CustomRenderMethodInput) {
      const g = context as WebGL2RenderingContext
      if (!map || !program) return
      if (pending) upload()
      if (!built?.count || !focus) return
      const matrix = localMatrix(map, focus.origin, args.modelViewProjectionMatrix as ArrayLike<number>)
      const { position, intensity, opacity, ground } = look()

      // the building on screen: its box's corners, projected (drawing-buffer pixels), and the depth of its middle
      const xray = screenBox(matrix, focus, g.drawingBufferWidth, g.drawingBufferHeight)
      const strength = Math.min(1, (performance.now() - openedAt) / FADE_MS)
      if (strength < 1) map.triggerRepaint()

      g.useProgram(program)
      g.uniformMatrix4fv(where.u_matrix, false, matrix)
      g.uniform3fv(where.u_lightpos, lightPosition(position, map.getBearing()))
      g.uniform1f(where.u_lightintensity, intensity)
      g.uniform1f(where.u_opacity, opacity)
      g.uniform3fv(where.u_ground, ground)
      g.uniform2f(where.u_centre, xray.centre[0], xray.centre[1])
      g.uniform2f(where.u_radius, Math.max(1, xray.radius[0]), Math.max(1, xray.radius[1]))
      g.uniform1f(where.u_soft, XRAY_SOFT)
      g.uniform1f(where.u_w, xray.w)
      g.uniform1f(where.u_depth, XRAY_DEPTH_M * xray.wPerMetre)
      g.uniform1f(where.u_grain, DITHER_CSS_PX * devicePixelRatio)
      g.uniform1f(where.u_strength, debug.xray ? strength : 0)

      g.bindBuffer(g.ARRAY_BUFFER, built.buffer)
      g.bindBuffer(g.ELEMENT_ARRAY_BUFFER, built.index)
      const stride = FLOATS * 4
      let offset = 0
      for (const [name, size] of [['a_pos', 2], ['a_normal', 3], ['a_t', 1], ['a_base', 1], ['a_height', 1], ['a_color', 3]] as const) {
        const at = attributes[name]
        if (at >= 0) {
          g.enableVertexAttribArray(at)
          g.vertexAttribPointer(at, size, g.FLOAT, false, stride, offset)
        }
        offset += size * 4
      }
      // the map's depth for 3D is set; the blocks are closed, so their back faces never show
      if (debug.front === 'none') g.disable(g.CULL_FACE)
      else g.enable(g.CULL_FACE)
      g.cullFace(g.BACK)
      g.frontFace(debug.front === 'CW' ? g.CW : g.CCW) // counter-clockwise from outside (measured: the map's y flip and its projection's cancel)
      g.disable(g.BLEND)
      g.drawElements(g.TRIANGLES, built.count, g.UNSIGNED_INT, 0)
      g.bindBuffer(g.ELEMENT_ARRAY_BUFFER, built.lines)
      g.drawElements(g.LINES, built.lineCount, g.UNSIGNED_INT, 0)
      for (const at of Object.values(attributes)) if (at >= 0) g.disableVertexAttribArray(at)
      g.disable(g.CULL_FACE)
    },
  }
}

/** The custom layer's matrix (world pixels) times the building's own frame (metres east and north of its origin, up
 * in metres), composed in double precision: world pixels at street zoom are past float32's precision. */
function localMatrix(map: MapLibreMap, origin: Focus['origin'], world: ArrayLike<number>): Float32Array {
  const size = 512 * 2 ** map.getZoom()
  const lat = (origin.lat * Math.PI) / 180
  const x = ((origin.lon + 180) / 360) * size
  const y = ((1 - Math.log(Math.tan(lat) + 1 / Math.cos(lat)) / Math.PI) / 2) * size
  const s = size / (2 * Math.PI * R * Math.cos(lat)) // pixels per metre at the building
  // world · translate(x, y, 0) · scale(s, -s, 1): columns of the result
  const out = new Float32Array(16)
  for (let row = 0; row < 4; row++) {
    const [a, b, c, d] = [world[row], world[4 + row], world[8 + row], world[12 + row]]
    out[row] = a * s
    out[4 + row] = -b * s
    out[8 + row] = c
    out[12 + row] = a * x + b * y + d
  }
  return out
}

function screenBox(matrix: Float32Array, focus: Focus, width: number, height: number) {
  let [x0, y0, x1, y1] = [Infinity, Infinity, -Infinity, -Infinity]
  for (const ring of focus.rings)
    for (const [x, y] of ring) {
      x0 = Math.min(x0, x)
      y0 = Math.min(y0, y)
      x1 = Math.max(x1, x)
      y1 = Math.max(y1, y)
    }
  const project = (x: number, y: number, z: number) => {
    const w = matrix[3] * x + matrix[7] * y + matrix[11] * z + matrix[15]
    return {
      px: (((matrix[0] * x + matrix[4] * y + matrix[8] * z + matrix[12]) / w) * 0.5 + 0.5) * width,
      py: (((matrix[1] * x + matrix[5] * y + matrix[9] * z + matrix[13]) / w) * 0.5 + 0.5) * height,
      w,
    }
  }
  let [p0, q0, p1, q1] = [Infinity, Infinity, -Infinity, -Infinity]
  for (const x of [x0, x1]) for (const y of [y0, y1]) for (const z of [0, focus.height]) {
    const { px, py } = project(x, y, z)
    p0 = Math.min(p0, px)
    q0 = Math.min(q0, py)
    p1 = Math.max(p1, px)
    q1 = Math.max(q1, py)
  }
  const middle = project((x0 + x1) / 2, (y0 + y1) / 2, focus.height / 2)
  // the rounded box round the building's box: its corners on the rim at 2^¼ the half sides, a little past them
  const k = 2 ** 0.25 * XRAY_MARGIN * 0.5
  return {
    centre: [(p0 + p1) / 2, (q0 + q1) / 2],
    radius: [(p1 - p0) * k, (q1 - q0) * k],
    w: middle.w,
    // clip w is the distance from the camera: how much of it a metre along the view adds
    wPerMetre: Math.max(Math.hypot(matrix[3], matrix[7], matrix[11]), 1e-12),
  }
}

/** MapLibre's light position: spherical [radius, azimuth, polar] → cartesian, turned with the map (anchor viewport). */
function lightPosition([r, azimuth, polar]: [number, number, number], bearing: number): Float32Array {
  const a = ((azimuth + 90) * Math.PI) / 180
  const p = (polar * Math.PI) / 180
  const [x, y, z] = [r * Math.cos(a) * Math.sin(p), r * Math.sin(a) * Math.sin(p), r * Math.cos(p)]
  const turn = (bearing * Math.PI) / 180
  const [c, s] = [Math.cos(turn), Math.sin(turn)]
  return new Float32Array([x * c - y * s, x * s + y * c, z])
}

/** Roofs, walls and footprints (fill and outline) of every block, in metres from the origin (x east, y north). Walls along a tile's edge are left
 * out: a block crossing it comes as two clipped pieces, and the cut between them is not a wall. */
function geometry(origin: Focus['origin'], blocks: Neighbour[]) {
  const vertices: number[] = []
  const indices: number[] = []
  const lines: number[] = []
  const lat = (origin.lat * Math.PI) / 180
  const toMetres = ([lng, latitude]: [number, number]): [number, number] => [
    (((lng - origin.lon) * Math.PI) / 180) * R * Math.cos(lat),
    (((latitude - origin.lat) * Math.PI) / 180) * R,
  ]
  const tiles = 2 ** TILE_ZOOM
  const tileX = (lng: number) => ((lng + 180) / 360) * tiles
  const tileY = (latitude: number) => {
    const l = (latitude * Math.PI) / 180
    return ((1 - Math.log(Math.tan(l) + 1 / Math.cos(l)) / Math.PI) / 2) * tiles
  }
  const onTileEdge = (u: number, v: number) => Math.abs(u - v) < 1e-9 && Math.min(u - Math.floor(u), Math.ceil(u) - u) < TILE_EDGE
  const vertex = (x: number, y: number, normal: [number, number, number], t: number, block: Neighbour) => {
    vertices.push(x, y, ...normal, t, block.base, block.top, ...block.colour)
    return vertices.length / FLOATS - 1
  }

  for (const block of blocks) {
    const rings = block.rings.map((ring) => {
      const open = ring.length > 1 && ring[0][0] === ring[ring.length - 1][0] && ring[0][1] === ring[ring.length - 1][1] ? ring.slice(0, -1) : ring
      return { lnglat: open, metres: open.map(toMetres) }
    })
    if (!rings[0] || rings[0].metres.length < 3) continue
    // roof: triangulated with its holes, every triangle turned to face up (counter-clockwise seen from above)
    const outer = rings[0].metres.map(([x, y]) => new Vector2(x, y))
    const holes = rings.slice(1).map((ring) => ring.metres.map(([x, y]) => new Vector2(x, y)))
    const all = [...outer, ...holes.flat()]
    const first = vertices.length / FLOATS
    for (const point of all) vertex(point.x, point.y, [0, 0, 1], 1, block)
    // and the footprint: the same triangles on the ground (shown only where the block is cut away)
    const ground = vertices.length / FLOATS
    for (const point of all) vertex(point.x, point.y, [0, 0, 1], 2, block)
    for (const [a, b, c] of ShapeUtils.triangulateShape(outer, holes)) {
      const area = (all[b].x - all[a].x) * (all[c].y - all[a].y) - (all[c].x - all[a].x) * (all[b].y - all[a].y)
      const [p, q] = area >= 0 ? [b, c] : [c, b]
      indices.push(first + a, first + p, first + q, ground + a, ground + p, ground + q)
    }
    // walls: each edge facing out of its own ring (out of the block for the outline, into the courtyard for a hole)
    for (const { lnglat, metres } of rings) {
      const turn = Math.sign(ShapeUtils.area(metres.map(([x, y]) => new Vector2(x, y)))) || 1
      for (let i = 0; i < metres.length; i++) {
        const j = (i + 1) % metres.length
        const [[ax, ay], [bx, by]] = [metres[i], metres[j]]
        const [la, lb] = [lnglat[i], lnglat[j]]
        if (onTileEdge(tileX(la[0]), tileX(lb[0])) || onTileEdge(tileY(la[1]), tileY(lb[1]))) continue
        const length = Math.hypot(bx - ax, by - ay)
        if (length < 1e-6) continue
        lines.push(vertex(ax, ay, [0, 0, 1], 3, block), vertex(bx, by, [0, 0, 1], 3, block))
        // outward in metres (x east, y north) is (dy, -dx)·turn for a counter-clockwise ring; in tile space y is south
        const [nx, ny] = [((by - ay) / length) * turn, (-(bx - ax) / length) * turn]
        const normal: [number, number, number] = [nx, -ny, 0]
        const a0 = vertex(ax, ay, normal, 0, block)
        const b0 = vertex(bx, by, normal, 0, block)
        const b1 = vertex(bx, by, normal, 1, block)
        const a1 = vertex(ax, ay, normal, 1, block)
        // counter-clockwise seen from outside: along a counter-clockwise ring's edge, then up, faces out
        if (turn > 0) indices.push(a0, b0, b1, a0, b1, a1)
        else indices.push(a0, b1, b0, a0, a1, b1)
      }
    }
  }
  return { vertices: new Float32Array(vertices), indices: new Uint32Array(indices), lines: new Uint32Array(lines) }
}

function link(gl: WebGL2RenderingContext, vertex: string, fragment: string) {
  const compile = (type: number, source: string) => {
    const shader = gl.createShader(type)!
    gl.shaderSource(shader, source)
    gl.compileShader(shader)
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(shader) ?? 'shader')
    return shader
  }
  const program = gl.createProgram()!
  gl.attachShader(program, compile(gl.VERTEX_SHADER, vertex))
  gl.attachShader(program, compile(gl.FRAGMENT_SHADER, fragment))
  gl.linkProgram(program)
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program) ?? 'program')
  return program
}
