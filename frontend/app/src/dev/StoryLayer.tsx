// The current answer drawn over the plan, without touching the plan's own colours: the route as a cased accent
// band (drawn in once) with start / destination / floor-change badges, the rooms the answer is about tinted and
// outlined in accent (pulsing a few times when they appear) with their names, a red hatch over closed rooms, lifts
// and stairs, dashed outlines around rooms that lost access, a ringed dot on each item asked about, and the walk
// outside to a nearby building. Lives inside the r3f canvas (StoryLayer) plus DOM badges over it (StoryMarkers).

import { useFrame, useThree } from '@react-three/fiber'
import { useEffect, useMemo, useRef } from 'react'
import * as THREE from 'three'
import type { GuideStep, Plan } from '../api'
import { ribbon, useZoomStep } from '../plan/bands'
import { toScene } from '../plan/geometry'
import type { PlanPalette } from '../plan/palette'
import { TurnIcon } from '../ui/TurnIcon'
import type { StepView, Story } from './story'
import { reducedMotion } from '../motion'
import './story.css'

const ROUTE_PX = 6
const CASING_PX = 10
const DOT_GAP_PX = 9 // between the dots of the walked part and of the steps still to come
const DOT_PX = 3.2 // their size
const COMET_PX = 34 // the light that runs along the step being walked: its length,
const COMET_SPEED_PX = 64 // its speed (px per second)
const COMET_REST_PX = 160 // and the pause before it runs again (as distance)
const CASING_OPACITY = 0.5
const STEP_EASE = 5 // how fast the walked part and the "you" puck catch up with a new step (1/s, exponential)
const FOCUS_PX = 3
const ROUTE_Y = 0.05
const DRAW_IN_SECONDS = 0.9
const OTHER_FLOOR_OPACITY = 0.35
const MAX_ITEM_DOTS = 24
const MAX_PLACE_LABELS = 6 // name badges on the rooms an answer is about
const MAX_ITEM_LABELS = 4 // and on its items, when there are this few
const FOCUS_FILL = 0.26
const PULSE_SECONDS = 2.4 // three soft pulses of the tint, then it stays

type Lift = (index: number) => number

// ---------- geometry ----------

function polygonGeometry(plan: Plan, polygons: [number, number][][], y: number) {
  const positions: number[] = []
  for (const polygon of polygons) {
    const contour = polygon.map(([x, z]) => new THREE.Vector2(x, z))
    if (THREE.ShapeUtils.isClockWise(contour)) contour.reverse()
    for (const [a, b, c] of THREE.ShapeUtils.triangulateShape(contour, [])) {
      for (const k of [a, c, b]) {
        const [X, Z] = toScene(plan, contour[k].x, contour[k].y)
        positions.push(X, y, Z)
      }
    }
  }
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
  return geometry
}

// ---------- route ----------

type Run = { floor: number; points: [number, number][]; offset: number }

/** One run per floor visited, with its distance from the start; a single-point visit in the middle (riding a lift
 * past a floor) is dropped. */
export function routeRuns(line: [number, number, number][]): Run[] {
  const runs: Run[] = []
  for (const [x, y, floor] of line) {
    const last = runs[runs.length - 1]
    if (last && last.floor === floor) last.points.push([x, y])
    else runs.push({ floor, points: [[x, y]], offset: 0 })
  }
  const kept = runs.filter((run, index) => run.points.length > 1 || index === 0 || index === runs.length - 1)
  let distance = 0
  for (const run of kept) {
    run.offset = distance
    for (let i = 1; i < run.points.length; i++) distance += Math.hypot(run.points[i][0] - run.points[i - 1][0], run.points[i][1] - run.points[i - 1][1])
  }
  return kept
}

/** The route line's shader: drawn in from the start (`progress`); before the guide starts, one solid line. While a
 * step is followed (`stepping`) only that step (`stepFrom` to `stepTo`) is solid, the walked part (to `done`) and the
 * steps still to come are dotted, and a short light runs along the solid part the way you go (`comet`; still under
 * reduced motion). The casing (`CASING`) is drawn under the solid part only. All lengths are metres along the line;
 * `pixel` is metres per screen pixel, so the marks keep their size on screen. */
export const routeMaterial = (colour: string, done: string, comet: boolean, casing = false) =>
  new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    side: THREE.DoubleSide,
    defines: casing ? { CASING: '' } : {},
    uniforms: {
      color: { value: new THREE.Color(colour) },
      doneColor: { value: new THREE.Color(done) },
      progress: { value: 0 },
      offset: { value: 0 },
      opacity: { value: 1 },
      time: { value: 0 },
      pixel: { value: 0.1 },
      bandHalf: { value: 0.3 },
      stepping: { value: 0 },
      done: { value: 0 },
      stepFrom: { value: 0 },
      stepTo: { value: 0 },
      total: { value: 0 },
      comet: { value: comet ? 1 : 0 },
    },
    vertexShader: `attribute float along; attribute float across; varying float vAlong; varying float vAcross;
      void main() { vAlong = along; vAcross = across; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
    fragmentShader: `uniform vec3 color; uniform vec3 doneColor; uniform float progress; uniform float offset; uniform float opacity;
      uniform float time; uniform float pixel; uniform float bandHalf; uniform float stepping; uniform float done;
      uniform float stepFrom; uniform float stepTo; uniform float total; uniform float comet;
      varying float vAlong; varying float vAcross;
      // a round dot every DOT_GAP px along the centre line, 0..1
      float dots(float a, float radius) {
        float spacing = ${DOT_GAP_PX.toFixed(1)} * pixel;
        float d = length(vec2(mod(a, spacing) - spacing * 0.5, vAcross));
        return 1.0 - smoothstep(radius - 0.7 * pixel, radius + 0.7 * pixel, d);
      }
      void main() {
        float a = vAlong + offset;
        if (a > progress) discard;
        bool following = stepping > 0.5;
        bool walked = following && a < done;
        bool later = following && a > stepTo;
        #ifdef CASING
        if (walked || later) discard;
        gl_FragColor = vec4(color, opacity * ${CASING_OPACITY.toFixed(2)});
        return;
        #endif
        float radius = ${(DOT_PX / 2).toFixed(2)} * pixel;
        if (walked) {
          float dot = dots(a, radius * 0.85);
          if (dot < 0.01) discard;
          gl_FragColor = vec4(doneColor, opacity * 0.75 * dot);
          return;
        }
        if (later) {
          float dot = dots(a, radius);
          if (dot < 0.01) discard;
          gl_FragColor = vec4(color, opacity * 0.6 * dot);
          return;
        }
        vec3 c = color;
        // the light: runs from the start of the solid part to its end, rests, runs again
        float lo = following ? stepFrom : 0.0;
        float hi = following ? stepTo : total;
        float tail = ${COMET_PX.toFixed(1)} * pixel;
        float cycle = (hi - lo) + tail + ${COMET_REST_PX.toFixed(1)} * pixel;
        float head = lo + mod(time * ${COMET_SPEED_PX.toFixed(1)} * pixel, cycle);
        float t = (head - a) / tail;
        if (comet > 0.5 && t >= 0.0 && t <= 1.0 && a >= lo && a <= hi) {
          float glow = (1.0 - t) * (1.0 - smoothstep(bandHalf * 0.5, bandHalf * 0.95, abs(vAcross)));
          c = mix(c, vec3(1.0), glow * 0.85);
        }
        gl_FragColor = vec4(c, opacity);
      }`,
  })

function Route({ plan, runs, palette, shown, floor, stacked, lift, routeKey, step }: {
  plan: Plan
  runs: Run[]
  palette: PlanPalette
  shown: number[]
  floor: number
  stacked: boolean
  lift: Lift
  routeKey: number
  step?: StepView
}) {
  const zoom = useZoomStep()
  const invalidate = useThree((state) => state.invalidate)
  const progress = useRef(0)
  const clock = useRef(0)
  // the walked part and the step's end as drawn: they ease to a new step instead of jumping
  const eased = useRef<{ done: number; from: number; to: number } | null>(null)
  const still = useMemo(() => reducedMotion(), [])
  const total = useMemo(() => {
    const last = runs[runs.length - 1]
    if (!last) return 0
    let length = last.offset
    for (let i = 1; i < last.points.length; i++) length += Math.hypot(last.points[i][0] - last.points[i - 1][0], last.points[i][1] - last.points[i - 1][1])
    return length
  }, [runs])

  const bands = useMemo(
    () =>
      runs
        .filter((run) => shown.includes(run.floor))
        .map((run) => {
          const points = run.points.map(([x, y]) => toScene(plan, x, y))
          const casing = ribbon(points, CASING_PX / zoom, ROUTE_Y - 0.005)
          const line = ribbon(points, ROUTE_PX / zoom, ROUTE_Y)
          const here = stacked || run.floor === floor
          const casingMaterial = routeMaterial(palette.halo, palette.halo, false, true)
          // the light runs only on the floor you are on: on the others the line is a faint reminder
          const lineMaterial = routeMaterial(palette.selectedEdge, palette.labelSoft, here)
          for (const material of [casingMaterial, lineMaterial]) {
            material.uniforms.offset.value = run.offset
            material.uniforms.opacity.value = here ? 1 : OTHER_FLOOR_OPACITY
            material.uniforms.pixel.value = 1 / zoom
            material.uniforms.bandHalf.value = ROUTE_PX / zoom / 2
            // the floor you are on draws its route over the low cut walls so a tilted camera never loses it; so does
            // every floor of a stack, so the whole route shows through the floors above it; in the single-floor
            // view the floors below keep depth so they never show through the floor above
            material.depthTest = !stacked && run.floor !== floor
          }
          return { run, casing, line, casingMaterial, lineMaterial }
        }),
    [plan, runs, shown, zoom, palette.halo, palette.selectedEdge, palette.labelSoft, stacked, floor],
  )
  useEffect(
    () => () =>
      bands.forEach((band) => [band.casing, band.line, band.casingMaterial, band.lineMaterial].forEach((item) => item.dispose())),
    [bands],
  )
  useEffect(() => {
    progress.current = 0
    invalidate()
  }, [routeKey, invalidate])
  useEffect(() => invalidate(), [step, invalidate])
  useFrame((_, delta) => {
    const tick = Math.min(delta, 1 / 30)
    if (progress.current < total) progress.current = Math.min(total, progress.current + (tick / DRAW_IN_SECONDS) * Math.max(total, 1))
    if (!still) clock.current += tick
    if (!step) eased.current = null
    else if (!eased.current || still) eased.current = { done: step.done, from: step.from, to: step.to }
    else {
      const k = 1 - Math.exp(-STEP_EASE * tick)
      const shown = eased.current
      shown.done += (step.done - shown.done) * k
      shown.from += (step.from - shown.from) * k
      shown.to += (step.to - shown.to) * k
      if (Math.abs(step.done - shown.done) + Math.abs(step.from - shown.from) + Math.abs(step.to - shown.to) < 0.02) eased.current = { done: step.done, from: step.from, to: step.to }
    }
    const easing = !!step && !!eased.current && (eased.current.done !== step.done || eased.current.from !== step.from || eased.current.to !== step.to)
    // drawn in: the end cap (which reaches past the last point) shows too
    const shownTo = progress.current >= total ? 1e9 : progress.current
    for (const band of bands) {
      for (const material of [band.casingMaterial, band.lineMaterial]) {
        material.uniforms.progress.value = shownTo
        material.uniforms.time.value = clock.current
        material.uniforms.stepping.value = step ? 1 : 0
        material.uniforms.done.value = eased.current?.done ?? 0
        material.uniforms.stepFrom.value = eased.current?.from ?? 0
        material.uniforms.stepTo.value = eased.current?.to ?? 0
        material.uniforms.total.value = total
      }
    }
    // the light runs as long as a route is drawn (on-demand frames: ask for the next one)
    if (progress.current < total || !still || easing) invalidate()
  })

  // where the route changes floor and both floors are drawn apart: a riser between them, as wide as the route and
  // cased like it, drawn over the floors so the slab in between never hides it
  const risers = useMemo(() => {
    const group = new THREE.Group()
    const up = new THREE.Vector3(0, 1, 0)
    for (let i = 0; i + 1 < runs.length; i++) {
      const a = runs[i]
      const b = runs[i + 1]
      if (!shown.includes(a.floor) || !shown.includes(b.floor) || lift(a.floor) === lift(b.floor)) continue
      const [ax, az] = toScene(plan, ...a.points[a.points.length - 1])
      const [bx, bz] = toScene(plan, ...b.points[0])
      const from = new THREE.Vector3(ax, lift(a.floor) + ROUTE_Y, az)
      const to = new THREE.Vector3(bx, lift(b.floor) + ROUTE_Y, bz)
      const length = from.distanceTo(to)
      for (const [px, colour, order] of [[CASING_PX, palette.halo, 7], [ROUTE_PX, palette.selectedEdge, 8]] as const) {
        const tube = new THREE.Mesh(
          new THREE.CylinderGeometry(px / zoom / 2, px / zoom / 2, length, 12),
          new THREE.MeshBasicMaterial({ color: colour, transparent: true, opacity: px === CASING_PX ? CASING_OPACITY : 1, depthTest: false, depthWrite: false }),
        )
        tube.position.copy(from).add(to).multiplyScalar(0.5)
        tube.quaternion.setFromUnitVectors(up, to.clone().sub(from).normalize())
        tube.renderOrder = order
        group.add(tube)
      }
    }
    return group
  }, [plan, runs, shown, lift, zoom, palette.halo, palette.selectedEdge])
  useEffect(() => () => {
    for (const tube of risers.children as THREE.Mesh[]) {
      tube.geometry.dispose()
      ;(tube.material as THREE.Material).dispose()
    }
  }, [risers])

  return (
    <>
      {bands.map((band, index) => (
        <group key={index} position={[0, lift(band.run.floor), 0]}>
          <mesh geometry={band.casing} material={band.casingMaterial} renderOrder={7} />
          <mesh geometry={band.line} material={band.lineMaterial} renderOrder={8} />
        </group>
      ))}
      <primitive object={risers} />
    </>
  )
}

// ---------- rooms ----------

function Outlines({ plan, ids, colour, floors, lift, dashed }: { plan: Plan; ids: string[]; colour: string; floors: number[]; lift: Lift; dashed?: boolean }) {
  const zoom = useZoomStep()
  const items = useMemo(() => {
    const wanted = new Set(ids)
    return plan.spaces
      .filter((space) => wanted.has(space.id) && floors.includes(space.floor))
      .map((space) => {
        const points = space.polygon.map(([x, z]) => toScene(plan, x, z))
        if (!dashed) return { floor: space.floor, object: new THREE.Mesh(ribbon([...points, points[0]], FOCUS_PX / zoom, 0.03), new THREE.MeshBasicMaterial({ color: colour, side: THREE.DoubleSide })) }
        const positions = points.flatMap(([X, Z], i) => {
          const [X2, Z2] = points[(i + 1) % points.length]
          return [X, 0.03, Z, X2, 0.03, Z2]
        })
        const geometry = new THREE.BufferGeometry()
        geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
        return { floor: space.floor, object: new THREE.LineSegments(geometry, new THREE.LineDashedMaterial({ color: colour, dashSize: 0.45, gapSize: 0.3 })).computeLineDistances() }
      })
  }, [plan, ids, colour, floors, lift, dashed, zoom])
  useEffect(() => () => items.forEach(({ object }) => {
    object.geometry.dispose()
    ;(object.material as THREE.Material).dispose()
  }), [items])
  return (
    <>
      {items.map(({ floor, object }, index) => (
        <group key={index} position={[0, lift(floor), 0]} renderOrder={6}>
          <primitive object={object} />
        </group>
      ))}
    </>
  )
}

/** The rooms an answer is about, tinted in the accent: pulses a few times when the answer arrives, then stays. */
function FocusFill({ plan, ids, colour, floors, lift, answerKey }: { plan: Plan; ids: string[]; colour: string; floors: number[]; lift: Lift; answerKey: number }) {
  const invalidate = useThree((state) => state.invalidate)
  const material = useMemo(() => new THREE.MeshBasicMaterial({ color: colour, transparent: true, opacity: FOCUS_FILL, depthWrite: false, side: THREE.DoubleSide }), [colour])
  const byFloor = useMemo(() => {
    const wanted = new Set(ids)
    const out = new Map<number, THREE.BufferGeometry>()
    for (const floor of floors) {
      const polygons = plan.spaces.filter((space) => space.floor === floor && wanted.has(space.id)).map((space) => space.polygon)
      if (polygons.length) out.set(floor, polygonGeometry(plan, polygons, 0.02))
    }
    return out
  }, [plan, ids, floors])
  const t = useRef(0)
  useEffect(() => {
    t.current = 0
    invalidate()
  }, [answerKey, invalidate])
  useFrame((_, delta) => {
    if (t.current >= PULSE_SECONDS) return
    t.current = Math.min(PULSE_SECONDS, t.current + Math.min(delta, 1 / 30))
    const wave = 0.5 - 0.5 * Math.cos((t.current / PULSE_SECONDS) * Math.PI * 6)
    material.opacity = FOCUS_FILL + wave * 0.3 * (1 - t.current / PULSE_SECONDS)
    invalidate()
  })
  useEffect(() => () => material.dispose(), [material])
  useEffect(() => () => byFloor.forEach((geometry) => geometry.dispose()), [byFloor])
  return (
    <>
      {[...byFloor].map(([floor, geometry]) => (
        <mesh key={floor} geometry={geometry} material={material} position={[0, lift(floor), 0]} renderOrder={5} />
      ))}
    </>
  )
}

/** A walk outside: a dashed accent line on the ground (from the exit to a nearby building's entrance, or from the
 * "you are here" figure outside to the nearest entrance). */
export function DashedWalk({ plan, from, to, floor, colour, lift }: { plan: Plan; from: [number, number]; to: [number, number]; floor: number; colour: string; lift: Lift }) {
  const line = useMemo(() => {
    const [ax, az] = toScene(plan, ...from)
    const [bx, bz] = toScene(plan, ...to)
    const geometry = new THREE.BufferGeometry()
    geometry.setAttribute('position', new THREE.Float32BufferAttribute([ax, ROUTE_Y, az, bx, ROUTE_Y, bz], 3))
    const material = new THREE.LineDashedMaterial({ color: colour, dashSize: 1.6, gapSize: 1.1, depthTest: false, transparent: true })
    return new THREE.Line(geometry, material).computeLineDistances()
  }, [plan, from, to, colour])
  useEffect(() => () => {
    line.geometry.dispose()
    ;(line.material as THREE.Material).dispose()
  }, [line])
  return (
    <group position={[0, lift(floor), 0]} renderOrder={9}>
      <primitive object={line} />
    </group>
  )
}

const hatchMaterial = (colour: string) =>
  new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    side: THREE.DoubleSide,
    uniforms: { color: { value: new THREE.Color(colour) } },
    vertexShader: `varying vec2 vWorld;
      void main() { vec4 w = modelMatrix * vec4(position, 1.0); vWorld = w.xz; gl_Position = projectionMatrix * viewMatrix * w; }`,
    fragmentShader: `uniform vec3 color; varying vec2 vWorld;
      void main() {
        float t = fract((vWorld.x + vWorld.y) / 0.7);
        float stripe = smoothstep(0.0, 0.08, t) * (1.0 - smoothstep(0.42, 0.5, t));
        gl_FragColor = vec4(color, 0.1 + stripe * 0.5);
      }`,
  })

/** Closed rooms, and every room of a closed lift or staircase, under a red hatch. */
function ClosedHatch({ plan, palette, floors, lift }: { plan: Plan; palette: PlanPalette; floors: number[]; lift: Lift }) {
  const material = useMemo(() => hatchMaterial(palette.materials.red), [palette.materials.red])
  const byFloor = useMemo(() => {
    const closed = new Set(plan.closed ?? [])
    const spaces = new Set(plan.spaces.filter((space) => closed.has(space.id)).map((space) => space.id))
    for (const connector of plan.connectors) if (closed.has(connector.id)) connector.spaces.forEach((id) => spaces.add(id))
    const out = new Map<number, THREE.BufferGeometry>()
    for (const floor of floors) {
      const polygons = plan.spaces.filter((space) => space.floor === floor && spaces.has(space.id)).map((space) => space.polygon)
      if (polygons.length) out.set(floor, polygonGeometry(plan, polygons, 0.015))
    }
    return out
  }, [plan, floors])
  useEffect(() => () => material.dispose(), [material])
  useEffect(() => () => byFloor.forEach((geometry) => geometry.dispose()), [byFloor])
  return (
    <>
      {[...byFloor].map(([floor, geometry]) => (
        <mesh key={floor} geometry={geometry} material={material} position={[0, lift(floor), 0]} renderOrder={3} />
      ))}
    </>
  )
}

// ---------- badges ----------

export type Marker = {
  key: string
  kind: 'start' | 'end' | 'change' | 'item' | 'you' | 'place' | 'next' | 'me' | 'goal' | 'move' | 'maybe'
  floor: number
  at: [number, number]
  label: string
  goto?: number
  /** 'maybe': the room a tap stands you in */
  space?: string
  /** 'you': a unit direction in the plan frame, drawn as the cone (projected, so it turns with the view) */
  ahead?: [number, number]
  stale?: boolean
  /** 'item': show its name too (few items) */
  named?: boolean
  /** 'goal': the move made there (the next step), for its arrow; 'move': the step on the card */
  turn?: GuideStep
  /** 'you': metres along the route's line, to glide there along the route */
  along?: number
}

/** Start, destination, each floor change (tap to follow it), and the items asked about. Floor-change names come
 * from the route's connector legs, in order. */
export function storyMarkers(plan: Plan, story: Story): Marker[] {
  const markers: Marker[] = []
  const route = story.route
  const runs = route ? routeRuns(route.line) : []
  const floorName = (index: number) => plan.floors[index]?.name ?? `Floor ${index}`
  if (route && runs.length) {
    const first = runs[0]
    const last = runs[runs.length - 1]
    // the first step's callout stands at the start already
    if (!story.move) markers.push({ key: 'start', kind: 'start', floor: first.floor, at: first.points[0], label: route.space_path[0] === 'outside' ? 'Entrance' : 'Start' })
    const arrive = route.legs.find((leg) => leg.kind === 'arrive')
    const end = route.next ? 'Exit' : arrive?.to_id === 'outside' ? 'Way out' : arrive?.to ?? 'Destination'
    markers.push({ key: 'end', kind: 'end', floor: last.floor, at: last.points[last.points.length - 1], label: end })
    const hops = route.legs.filter((leg) => leg.kind === 'connector')
    for (let i = 0; i + 1 < runs.length; i++) {
      const from = runs[i]
      const to = runs[i + 1]
      const up = hops[i]?.up ?? (plan.floors[to.floor]?.level ?? 0) > (plan.floors[from.floor]?.level ?? 0)
      markers.push({ key: `hop${i}`, kind: 'change', floor: from.floor, at: from.points[from.points.length - 1], goto: to.floor, label: `${up ? '↑' : '↓'} ${hops[i]?.via ?? 'Stairs or lift'} to ${floorName(to.floor)}` })
      markers.push({ key: `land${i}`, kind: 'change', floor: to.floor, at: to.points[0], goto: from.floor, label: `From ${floorName(from.floor)}` })
    }
  }
  const items = new Set(story.assets)
  const named = story.assets.length <= MAX_ITEM_LABELS
  for (const asset of plan.assets) {
    if (items.has(asset.id) && markers.length < MAX_ITEM_DOTS) markers.push({ key: `item-${asset.id}`, kind: 'item', floor: asset.floor, at: asset.position, label: asset.name, named })
  }
  // the rooms an answer is about, by name (a route names its destination already; rooms holding named items too)
  if (!route) {
    const holding = new Set(named ? plan.assets.filter((asset) => items.has(asset.id)).map((asset) => asset.space) : [])
    const wanted = new Set(story.focus.filter((id) => !holding.has(id) && !story.maybe?.includes(id)))
    for (const space of plan.spaces.filter((item) => wanted.has(item.id)).slice(0, MAX_PLACE_LABELS))
      markers.push({ key: `place-${space.id}`, kind: 'place', floor: space.floor, at: space.label, label: space.name })
  }
  // the end of the step being followed, where the next move happens (the route's own end has its badge already)
  const step = story.step
  if (route && step && step.next && step.to - step.from > 0.5) markers.push({ key: 'goal', kind: 'goal', floor: step.floor, at: step.end, label: step.next.text, turn: step.next })
  // the step on the card, where it is made
  if (route && story.move) markers.push({ key: 'move', kind: 'move', floor: story.move.floor, at: story.move.at, label: story.move.step.text, turn: story.move.step })
  if (story.outdoor) markers.push({ key: 'next', kind: 'next', floor: story.outdoor.floor, at: story.outdoor.to, label: story.outdoor.label })
  // where you might be (your position not known): tap the right one
  const maybe = new Set(story.maybe ?? [])
  for (const space of plan.spaces.filter((item) => maybe.has(item.id)))
    markers.push({ key: `maybe-${space.id}`, kind: 'maybe', floor: space.floor, at: space.label, label: space.name, space: space.id })
  if (story.you) markers.push({ key: 'you', kind: 'you', floor: story.you.floor, at: story.you.at, ahead: story.you.ahead, stale: story.you.stale, along: story.you.along, label: 'You' })
  return markers
}

/** What a marker does when tapped or dragged: a floor change goes to its floor, the next-building badge continues
 * there, and the "you are here" figure (`me`) is dragged to a new place (x, y relative to the plan's box). */
export type MarkerActions = {
  onGoto: (floor: number) => void
  onNext?: () => void
  onMeDrop?: (x: number, y: number) => void
  /** while the figure is dragged: where it would land there (its label), shown on the figure */
  onMePreview?: (x: number, y: number) => string | null
  /** a "you might be here" badge tapped: stand in that room */
  onMaybe?: (space: string) => void
}

export function StoryMarkers({ markers, elements, onGoto, onNext, onMeDrop, onMePreview, onMaybe }: { markers: Marker[]; elements: React.RefObject<Map<string, HTMLElement>> } & MarkerActions) {
  return (
    <div className="story-markers">
      {markers.map((marker) => {
        const ref = (node: HTMLElement | null) => {
          if (node) elements.current.set(marker.key, node)
          else elements.current.delete(marker.key)
        }
        const goto = marker.goto
        return (
          <div key={marker.key} ref={ref} className={`story-marker ${marker.kind}`}>
            {marker.kind === 'change' && goto !== undefined ? (
              <button
                type="button"
                onPointerDown={(event) => event.stopPropagation()}
                onPointerUp={(event) => event.stopPropagation()}
                onClick={() => onGoto(goto)}
              >
                {marker.label}
              </button>
            ) : marker.kind === 'next' ? (
              <button
                type="button"
                onPointerDown={(event) => event.stopPropagation()}
                onPointerUp={(event) => event.stopPropagation()}
                onClick={() => onNext?.()}
              >
                {marker.label}
              </button>
            ) : marker.kind === 'maybe' && marker.space ? (
              <button
                type="button"
                onPointerDown={(event) => event.stopPropagation()}
                onPointerUp={(event) => event.stopPropagation()}
                onClick={() => onMaybe?.(marker.space!)}
                aria-label={`I'm in ${marker.label}`}
              >
                <PersonGlyph size={14} /> Here? · {marker.label}
              </button>
            ) : marker.kind === 'me' ? (
              <MeFigure label={marker.label} onDrop={onMeDrop} onPreview={onMePreview} />
            ) : marker.kind === 'item' ? (
              <>
                <i title={marker.label} />
                {marker.named && <span>{marker.label}</span>}
              </>
            ) : marker.kind === 'goal' && marker.turn ? (
              <div key={marker.label} className="then" title={marker.label}>
                then <TurnIcon leg={marker.turn} size={12} stroke={2.6} /> {thenWhere(marker.turn)}
              </div>
            ) : marker.kind === 'move' && marker.turn ? (
              <MoveCallout key={marker.label} step={marker.turn} />
            ) : marker.kind === 'you' ? (
              <b className={marker.stale ? 'stale' : ''} aria-label={marker.stale ? 'You, roughly' : 'You'}>
                <em />
              </b>
            ) : (
              <span>{marker.label}</span>
            )}
          </div>
        )
      })}
    </div>
  )
}

const TURN_WORD = { left: 'Turn left', right: 'Turn right', back: 'Turn around', straight: 'Straight on' } as const

/** Where the next step goes, in a word or two, for the "then …" tag at the end of the step being walked. */
function thenWhere(step: GuideStep): string {
  if (step.kind === 'arrive') return step.to_id === 'outside' ? 'outside' : 'arrive'
  if (step.kind === 'connector') return `${step.via ?? 'stairs'} ${step.up ? 'up' : 'down'}`
  if (step.kind === 'exit') return 'out'
  return step.to
}

/** The step on the card, as a callout pinned where it is made: its arrow, the move and metres, where it leads. */
function MoveCallout({ step }: { step: GuideStep }) {
  const [head, sub] =
    step.kind === 'arrive'
      ? [step.to_id === 'outside' ? 'Outside' : step.to, 'You have arrived']
      : step.kind === 'connector'
        ? [`${step.via ?? 'Stairs'} ${step.up ? 'up' : 'down'}`, `to ${step.floor}`]
        : [
            `${TURN_WORD[step.turn]}${step.metres > 0 ? ` · ${step.metres} m` : ''}`,
            `${step.kind === 'exit' ? 'and leave the building' : `into ${step.to}`}${step.landmark ? ` · by the ${step.landmark}` : ''}`,
          ]
  return (
    <div className={`callout ${step.kind}`}>
      <b>
        <TurnIcon leg={step} size={17} stroke={2.6} />
      </b>
      <div>
        <strong>{head}</strong>
        <small>{sub}</small>
      </div>
    </div>
  )
}

/** The "you are here" figure on the plan: drag it to where you are. While dragged it follows the pointer itself
 * (the marker tracker leaves a dragged marker alone); dropped, the plan places it (onDrop) and the tracker takes over. */
export function MeFigure({ label, onDrop, onPreview }: { label: string; onDrop?: (x: number, y: number) => void; onPreview?: (x: number, y: number) => string | null }) {
  const name = useRef<HTMLSpanElement>(null)
  const end = (marker: HTMLElement) => {
    delete marker.dataset.dragging
    marker.classList.remove('dragging')
    if (name.current) name.current.textContent = label // the preview wrote over it; a new label re-renders anyway
  }
  return (
    <button
      type="button"
      className="me-figure"
      aria-label={`You are here: ${label}. Drag to move.`}
      title="Drag me to where you are"
      onPointerDown={(event) => {
        event.stopPropagation()
        const marker = event.currentTarget.parentElement
        const box = marker?.parentElement?.getBoundingClientRect()
        if (!marker || !box) return
        event.currentTarget.setPointerCapture(event.pointerId)
        marker.dataset.dragging = 'true'
        marker.classList.add('dragging')
      }}
      onPointerMove={(event) => {
        const marker = event.currentTarget.parentElement
        const box = marker?.parentElement?.getBoundingClientRect()
        if (!marker || !box || marker.dataset.dragging !== 'true') return
        const [x, y] = [event.clientX - box.left, event.clientY - box.top]
        marker.style.transform = `translate(${x}px, ${y}px)`
        if (onPreview && name.current) name.current.textContent = onPreview(x, y) ?? 'Not here'
      }}
      onPointerUp={(event) => {
        event.stopPropagation()
        const marker = event.currentTarget.parentElement
        const box = marker?.parentElement?.getBoundingClientRect()
        if (!marker || !box || marker.dataset.dragging !== 'true') return
        end(marker)
        onDrop?.(event.clientX - box.left, event.clientY - box.top)
      }}
      onPointerCancel={(event) => {
        const marker = event.currentTarget.parentElement
        if (marker) end(marker)
      }}
    >
      <PersonGlyph />
      <span ref={name}>{label}</span>
    </button>
  )
}

/** A standing person (lucide "person-standing"), inline so the figure needs no icon import here. */
export function PersonGlyph({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="5" r="1" />
      <path d="m9 20 3-6 3 6" />
      <path d="m6 8 6 2 6-2" />
      <path d="M12 10v4" />
    </svg>
  )
}

/** The point `metres` along the route's runs (clamped to its ends), with its floor. */
function pointAlong(runs: Run[], metres: number): { at: [number, number]; floor: number } | null {
  for (let r = 0; r < runs.length; r++) {
    const { points, offset, floor } = runs[r]
    let distance = offset
    for (let i = 1; i < points.length; i++) {
      const [ax, ay] = points[i - 1]
      const [bx, by] = points[i]
      const length = Math.hypot(bx - ax, by - ay)
      if (metres <= distance + length || (r === runs.length - 1 && i === points.length - 1)) {
        const t = length > 0 ? Math.max(0, Math.min(1, (metres - distance) / length)) : 0
        return { at: [ax + (bx - ax) * t, ay + (by - ay) * t], floor }
      }
      distance += length
    }
    // a floor change: between two runs the puck waits at the end of this one
    const next = runs[r + 1]
    if (next && metres < next.offset) return { at: points[points.length - 1], floor }
  }
  return runs.length ? { at: runs[0].points[0], floor: runs[0].floor } : null
}

const GLIDE_MAX_M = 80 // a jump farther than this (a new route, a fix far away) is not glided
const CALLOUT_GAP_PX = 26 // the step's callout starts this far right of its point (hud.css .story-marker.move)
const EDGE_PX = 80 // the floor rail and the round buttons along the right edge
const SIDE_PX = 12 // and the left edge's margin
const CALLOUT_RISE_PX = 58 // above the point when it fits on neither side

function MarkerTracker({ plan, markers, elements, floors, lift, runs }: { plan: Plan; markers: Marker[]; elements: React.RefObject<Map<string, HTMLElement>>; floors: number[]; lift: Lift; runs: Run[] }) {
  const { camera, size, invalidate } = useThree()
  const point = useMemo(() => new THREE.Vector3(), [])
  // where the "you" puck is drawn, in metres along the route: it glides to a new step instead of jumping
  const glide = useRef<{ runs: Run[]; along: number } | null>(null)
  const still = useMemo(() => reducedMotion(), [])
  useFrame((_, delta) => {
    for (const marker of markers) {
      const node = elements.current.get(marker.key)
      if (!node || node.dataset.dragging) continue
      let { at, floor } = marker
      if (marker.along !== undefined && runs.length) {
        const shown = glide.current
        if (!shown || shown.runs !== runs || still || Math.abs(shown.along - marker.along) > GLIDE_MAX_M) glide.current = { runs, along: marker.along }
        else {
          shown.along += (marker.along - shown.along) * (1 - Math.exp(-STEP_EASE * Math.min(delta, 1 / 30)))
          if (Math.abs(marker.along - shown.along) < 0.02) shown.along = marker.along
          else invalidate()
        }
        const placed = pointAlong(runs, glide.current!.along)
        if (placed) ({ at, floor } = placed)
      }
      const [X, Z] = toScene(plan, at[0], at[1])
      point.set(X, lift(floor) + ROUTE_Y, Z).project(camera)
      const x = ((point.x + 1) / 2) * size.width
      const y = ((1 - point.y) / 2) * size.height
      node.style.transform = `translate(${x}px, ${y}px)`
      // the step's callout: right of its point, else left of it, else above it, always clear of the screen's edges
      if (marker.kind === 'move') {
        const box = node.firstElementChild as HTMLElement | null
        const width = box?.offsetWidth ?? 0
        const right = x + CALLOUT_GAP_PX
        const left = x - CALLOUT_GAP_PX - width
        const [dx, dy] = right + width <= size.width - EDGE_PX ? [CALLOUT_GAP_PX, 0]
          : left >= SIDE_PX ? [-CALLOUT_GAP_PX - width, 0]
          : [Math.max(SIDE_PX, Math.min(size.width - EDGE_PX - width, x - width / 2)) - x, -CALLOUT_RISE_PX]
        node.style.setProperty('--callout-x', `${dx}px`)
        node.style.setProperty('--callout-y', `${dy}px`)
      }
      if (marker.ahead) {
        // the cone points where the route goes on, as seen on screen
        const [AX, AZ] = toScene(plan, at[0] + marker.ahead[0], at[1] + marker.ahead[1])
        point.set(AX, lift(floor) + ROUTE_Y, AZ).project(camera)
        const ax = ((point.x + 1) / 2) * size.width
        const ay = ((1 - point.y) / 2) * size.height
        node.style.setProperty('--heading', `${Math.atan2(ay - y, ax - x) + Math.PI / 2}rad`)
      }
      node.style.visibility = floors.includes(floor) && x > -40 && y > -40 && x < size.width + 40 && y < size.height + 40 ? 'visible' : 'hidden'
    }
  })
  useEffect(() => invalidate(), [markers, floors, invalidate])
  return null
}

// ---------- the layer ----------

/** Everything above, for the floors on screen. `shown` = floors drawn, `floor` = the one you are on. */
export function StoryLayer({ plan, story, palette, shown, floor, stacked, lift, markers, markerElements }: {
  plan: Plan
  story: Story
  palette: PlanPalette
  shown: number[]
  floor: number
  stacked: boolean
  lift: Lift
  markers: Marker[]
  markerElements: React.RefObject<Map<string, HTMLElement>>
}) {
  const key = shown.join(',')
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const floors = useMemo(() => shown, [key])
  const runs = useMemo(() => (story.route ? routeRuns(story.route.line) : []), [story.route])
  const here = useMemo(() => (stacked ? floors : [floor]), [stacked, floors, floor])
  // a room you might be in is drawn as that (orange, dashed), not also as part of the answer (blue)
  const focus = useMemo(() => (story.maybe?.length ? story.focus.filter((id) => !story.maybe!.includes(id)) : story.focus), [story.focus, story.maybe])
  return (
    <>
      <ClosedHatch plan={plan} palette={palette} floors={floors} lift={lift} />
      {story.lost.length > 0 && <Outlines plan={plan} ids={story.lost} colour={palette.labelSoft} floors={floors} lift={lift} dashed />}
      {!!story.maybe?.length && <Outlines plan={plan} ids={story.maybe} colour={palette.me} floors={here} lift={lift} dashed />}
      {focus.length > 0 && !story.route && <FocusFill plan={plan} ids={focus} colour={palette.selectedEdge} floors={here} lift={lift} answerKey={story.key} />}
      {focus.length > 0 && <Outlines plan={plan} ids={focus} colour={palette.selectedEdge} floors={here} lift={lift} />}
      {runs.length > 0 && <Route plan={plan} runs={runs} palette={palette} shown={floors} floor={floor} stacked={stacked} lift={lift} routeKey={story.key} step={story.step} />}
      {story.outdoor && floors.includes(story.outdoor.floor) && (
        <DashedWalk plan={plan} from={story.outdoor.from} to={story.outdoor.to} floor={story.outdoor.floor} colour={palette.selectedEdge} lift={lift} />
      )}
      <MarkerTracker plan={plan} markers={markers} elements={markerElements} floors={here} lift={lift} runs={runs} />
    </>
  )
}
