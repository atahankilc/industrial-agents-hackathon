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

const ROUTE_PX = 10
const CASING_PX = 15
const ARROW_GAP_PX = 30 // between the chevrons on the route band
const ARROW_SPEED_PX = 26 // how fast they flow the way you go, px per second
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

/** The route band's shader: drawn in from the start (`progress`), white chevrons flowing the way you go, and while a
 * step is followed (`stepping`) the walked part greyed out and the chevrons only on the step being walked. All
 * lengths are metres along the line; `pixel` is metres per screen pixel, so the marks keep their size on screen. */
const routeMaterial = (colour: string, done: string, arrows: boolean) =>
  new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    side: THREE.DoubleSide,
    defines: arrows ? { ARROWS: '' } : {},
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
      stepTo: { value: 0 },
    },
    vertexShader: `attribute float along; attribute float across; varying float vAlong; varying float vAcross;
      void main() { vAlong = along; vAcross = across; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
    fragmentShader: `uniform vec3 color; uniform vec3 doneColor; uniform float progress; uniform float offset; uniform float opacity;
      uniform float time; uniform float pixel; uniform float bandHalf; uniform float stepping; uniform float done; uniform float stepTo;
      varying float vAlong; varying float vAcross;
      void main() {
        float a = vAlong + offset;
        if (a > progress) discard;
        bool walked = stepping > 0.5 && a < done;
        vec3 c = walked ? doneColor : color;
        float alpha = opacity * (walked ? 0.7 : 1.0);
        #ifdef ARROWS
        if (!walked && (stepping < 0.5 || a <= stepTo)) {
          float spacing = ${ARROW_GAP_PX.toFixed(1)} * pixel;
          float s = mod(a - time * ${ARROW_SPEED_PX.toFixed(1)} * pixel, spacing);
          float side = abs(vAcross);
          // a chevron: its tip mid-band, its arms swept back at 45 degrees
          float d = abs(s - spacing * 0.5 + side);
          float stroke = 1.4 * pixel;
          float mark = (1.0 - smoothstep(stroke - 0.6 * pixel, stroke + 0.6 * pixel, d)) * (1.0 - smoothstep(bandHalf * 0.6, bandHalf * 0.8, side));
          c = mix(c, vec3(1.0), mark * 0.95);
        }
        #endif
        gl_FragColor = vec4(c, alpha);
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
  const still = useMemo(() => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false, [])
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
          const casingMaterial = routeMaterial(palette.halo, palette.halo, false)
          // chevrons only on the floor you are on: on the others the band is a faint reminder
          const lineMaterial = routeMaterial(palette.selectedEdge, palette.labelSoft, here)
          for (const material of [casingMaterial, lineMaterial]) {
            material.uniforms.offset.value = run.offset
            material.uniforms.opacity.value = here ? 1 : OTHER_FLOOR_OPACITY
            material.uniforms.pixel.value = 1 / zoom
            material.uniforms.bandHalf.value = ROUTE_PX / zoom / 2
            // the floor you are on draws its route over the low cut walls so a tilted camera never loses it; other
            // floors keep depth so they never show through the floor above
            material.depthTest = stacked || run.floor !== floor
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
    // drawn in: the end cap (which reaches past the last point) shows too
    const shownTo = progress.current >= total ? 1e9 : progress.current
    for (const band of bands) {
      for (const material of [band.casingMaterial, band.lineMaterial]) {
        material.uniforms.progress.value = shownTo
        material.uniforms.time.value = clock.current
        material.uniforms.stepping.value = step ? 1 : 0
        material.uniforms.done.value = step?.done ?? 0
        material.uniforms.stepTo.value = step?.to ?? 0
      }
    }
    // the chevrons flow as long as a route is drawn (on-demand frames: ask for the next one)
    if (progress.current < total || !still) invalidate()
  })

  // where the route changes floor and both floors are drawn apart: a dashed riser between them
  const risers = useMemo(() => {
    const positions: number[] = []
    for (let i = 0; i + 1 < runs.length; i++) {
      const a = runs[i]
      const b = runs[i + 1]
      if (!shown.includes(a.floor) || !shown.includes(b.floor) || lift(a.floor) === lift(b.floor)) continue
      const [ax, az] = toScene(plan, ...a.points[a.points.length - 1])
      const [bx, bz] = toScene(plan, ...b.points[0])
      positions.push(ax, lift(a.floor) + ROUTE_Y, az, bx, lift(b.floor) + ROUTE_Y, bz)
    }
    const geometry = new THREE.BufferGeometry()
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
    return new THREE.LineSegments(geometry, new THREE.LineDashedMaterial({ color: palette.selectedEdge, dashSize: 0.3, gapSize: 0.2 })).computeLineDistances()
  }, [plan, runs, shown, lift, palette.selectedEdge])
  useEffect(() => () => {
    risers.geometry.dispose()
    ;(risers.material as THREE.Material).dispose()
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
  kind: 'start' | 'end' | 'change' | 'item' | 'you' | 'place' | 'next' | 'me' | 'goal'
  floor: number
  at: [number, number]
  label: string
  goto?: number
  /** 'you': a unit direction in the plan frame, drawn as the cone (projected, so it turns with the view) */
  ahead?: [number, number]
  stale?: boolean
  /** 'item': show its name too (few items) */
  named?: boolean
  /** 'goal': the move made there (the next step), for its arrow */
  turn?: GuideStep
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
    markers.push({ key: 'start', kind: 'start', floor: first.floor, at: first.points[0], label: route.space_path[0] === 'outside' ? 'Entrance' : 'Start' })
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
    const wanted = new Set(story.focus.filter((id) => !holding.has(id)))
    for (const space of plan.spaces.filter((item) => wanted.has(item.id)).slice(0, MAX_PLACE_LABELS))
      markers.push({ key: `place-${space.id}`, kind: 'place', floor: space.floor, at: space.label, label: space.name })
  }
  // the end of the step being followed, where the next move happens (the route's own end has its badge already)
  const step = story.step
  if (route && step && step.next && step.to - step.from > 0.5) markers.push({ key: 'goal', kind: 'goal', floor: step.floor, at: step.end, label: step.next.text, turn: step.next })
  if (story.outdoor) markers.push({ key: 'next', kind: 'next', floor: story.outdoor.floor, at: story.outdoor.to, label: story.outdoor.label })
  if (story.you) markers.push({ key: 'you', kind: 'you', floor: story.you.floor, at: story.you.at, ahead: story.you.ahead, stale: story.you.stale, label: 'You' })
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
}

export function StoryMarkers({ markers, elements, onGoto, onNext, onMeDrop, onMePreview }: { markers: Marker[]; elements: React.RefObject<Map<string, HTMLElement>> } & MarkerActions) {
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
            ) : marker.kind === 'me' ? (
              <MeFigure label={marker.label} onDrop={onMeDrop} onPreview={onMePreview} />
            ) : marker.kind === 'item' ? (
              <>
                <i title={marker.label} />
                {marker.named && <span>{marker.label}</span>}
              </>
            ) : marker.kind === 'goal' && marker.turn ? (
              <b key={marker.label} title={marker.label}>
                <TurnIcon leg={marker.turn} size={18} stroke={2.4} />
              </b>
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

function MarkerTracker({ plan, markers, elements, floors, lift }: { plan: Plan; markers: Marker[]; elements: React.RefObject<Map<string, HTMLElement>>; floors: number[]; lift: Lift }) {
  const { camera, size, invalidate } = useThree()
  const point = useMemo(() => new THREE.Vector3(), [])
  useFrame(() => {
    for (const marker of markers) {
      const node = elements.current.get(marker.key)
      if (!node || node.dataset.dragging) continue
      const [X, Z] = toScene(plan, marker.at[0], marker.at[1])
      point.set(X, lift(marker.floor) + ROUTE_Y, Z).project(camera)
      const x = ((point.x + 1) / 2) * size.width
      const y = ((1 - point.y) / 2) * size.height
      node.style.transform = `translate(${x}px, ${y}px)`
      if (marker.ahead) {
        // the cone points where the route goes on, as seen on screen
        const [AX, AZ] = toScene(plan, marker.at[0] + marker.ahead[0], marker.at[1] + marker.ahead[1])
        point.set(AX, lift(marker.floor) + ROUTE_Y, AZ).project(camera)
        const ax = ((point.x + 1) / 2) * size.width
        const ay = ((1 - point.y) / 2) * size.height
        node.style.setProperty('--heading', `${Math.atan2(ay - y, ax - x) + Math.PI / 2}rad`)
      }
      node.style.visibility = floors.includes(marker.floor) && x > -40 && y > -40 && x < size.width + 40 && y < size.height + 40 ? 'visible' : 'hidden'
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
  return (
    <>
      <ClosedHatch plan={plan} palette={palette} floors={floors} lift={lift} />
      {story.lost.length > 0 && <Outlines plan={plan} ids={story.lost} colour={palette.labelSoft} floors={floors} lift={lift} dashed />}
      {story.focus.length > 0 && !story.route && <FocusFill plan={plan} ids={story.focus} colour={palette.selectedEdge} floors={here} lift={lift} answerKey={story.key} />}
      {story.focus.length > 0 && <Outlines plan={plan} ids={story.focus} colour={palette.selectedEdge} floors={here} lift={lift} />}
      {runs.length > 0 && <Route plan={plan} runs={runs} palette={palette} shown={floors} floor={floor} stacked={stacked} lift={lift} routeKey={story.key} step={story.step} />}
      {story.outdoor && floors.includes(story.outdoor.floor) && (
        <DashedWalk plan={plan} from={story.outdoor.from} to={story.outdoor.to} floor={story.outdoor.floor} colour={palette.selectedEdge} lift={lift} />
      )}
      <MarkerTracker plan={plan} markers={markers} elements={markerElements} floors={here} lift={lift} />
    </>
  )
}
