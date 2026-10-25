// The current answer drawn over the plan, without touching the plan's own colours: the route as a cased accent
// band (drawn in once) with start / destination / floor-change badges, accent outlines around the rooms the answer
// is about, a red hatch over closed rooms, lifts and stairs, dashed outlines around rooms that lost access, and a
// dot on each item asked about. Lives inside the r3f canvas (StoryLayer) plus DOM badges over it (StoryMarkers).

import { useFrame, useThree } from '@react-three/fiber'
import { useEffect, useMemo, useRef } from 'react'
import * as THREE from 'three'
import type { Plan } from '../api'
import { ribbon, useZoomStep } from '../plan/bands'
import { toScene } from '../plan/geometry'
import type { PlanPalette } from '../plan/palette'
import type { Story } from './story'

const ROUTE_PX = 7
const CASING_PX = 12
const FOCUS_PX = 3
const ROUTE_Y = 0.05
const DRAW_IN_SECONDS = 0.9
const OTHER_FLOOR_OPACITY = 0.35
const MAX_ITEM_DOTS = 24

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

const routeMaterial = (colour: string) =>
  new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    side: THREE.DoubleSide,
    uniforms: { color: { value: new THREE.Color(colour) }, progress: { value: 0 }, offset: { value: 0 }, opacity: { value: 1 } },
    vertexShader: `attribute float along; varying float vAlong;
      void main() { vAlong = along; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
    fragmentShader: `uniform vec3 color; uniform float progress; uniform float offset; uniform float opacity; varying float vAlong;
      void main() { if (vAlong + offset > progress) discard; gl_FragColor = vec4(color, opacity); }`,
  })

function Route({ plan, runs, palette, shown, floor, stacked, lift, routeKey }: {
  plan: Plan
  runs: Run[]
  palette: PlanPalette
  shown: number[]
  floor: number
  stacked: boolean
  lift: Lift
  routeKey: number
}) {
  const zoom = useZoomStep()
  const invalidate = useThree((state) => state.invalidate)
  const progress = useRef(0)
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
          const casingMaterial = routeMaterial(palette.halo)
          const lineMaterial = routeMaterial(palette.selectedEdge)
          for (const material of [casingMaterial, lineMaterial]) {
            material.uniforms.offset.value = run.offset
            material.uniforms.opacity.value = stacked || run.floor === floor ? 1 : OTHER_FLOOR_OPACITY
            // the floor you are on draws its route over the low cut walls so a tilted camera never loses it; other
            // floors keep depth so they never show through the floor above
            material.depthTest = stacked || run.floor !== floor
          }
          return { run, casing, line, casingMaterial, lineMaterial }
        }),
    [plan, runs, shown, zoom, palette.halo, palette.selectedEdge, stacked, floor],
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
  useFrame((_, delta) => {
    if (progress.current < total) {
      progress.current = Math.min(total, progress.current + (Math.min(delta, 1 / 30) / DRAW_IN_SECONDS) * Math.max(total, 1))
      invalidate()
    }
    for (const band of bands) {
      band.casingMaterial.uniforms.progress.value = progress.current
      band.lineMaterial.uniforms.progress.value = progress.current
    }
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
  kind: 'start' | 'end' | 'change' | 'item' | 'you'
  floor: number
  at: [number, number]
  label: string
  goto?: number
  /** 'you': a unit direction in the plan frame, drawn as the cone (projected, so it turns with the view) */
  ahead?: [number, number]
  stale?: boolean
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
    markers.push({ key: 'end', kind: 'end', floor: last.floor, at: last.points[last.points.length - 1], label: arrive?.to ?? 'Destination' })
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
  for (const asset of plan.assets) {
    if (items.has(asset.id) && markers.length < MAX_ITEM_DOTS) markers.push({ key: `item-${asset.id}`, kind: 'item', floor: asset.floor, at: asset.position, label: asset.name })
  }
  if (story.you) markers.push({ key: 'you', kind: 'you', floor: story.you.floor, at: story.you.at, ahead: story.you.ahead, stale: story.you.stale, label: 'You' })
  return markers
}

export function StoryMarkers({ markers, elements, onGoto }: { markers: Marker[]; elements: React.RefObject<Map<string, HTMLElement>>; onGoto: (floor: number) => void }) {
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
            ) : marker.kind === 'item' ? (
              <i title={marker.label} />
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

function MarkerTracker({ plan, markers, elements, floors, lift }: { plan: Plan; markers: Marker[]; elements: React.RefObject<Map<string, HTMLElement>>; floors: number[]; lift: Lift }) {
  const { camera, size, invalidate } = useThree()
  const point = useMemo(() => new THREE.Vector3(), [])
  useFrame(() => {
    for (const marker of markers) {
      const node = elements.current.get(marker.key)
      if (!node) continue
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
      {story.focus.length > 0 && <Outlines plan={plan} ids={story.focus} colour={palette.selectedEdge} floors={here} lift={lift} />}
      {runs.length > 0 && <Route plan={plan} runs={runs} palette={palette} shown={floors} floor={floor} stacked={stacked} lift={lift} routeKey={story.key} />}
      <MarkerTracker plan={plan} markers={markers} elements={markerElements} floors={here} lift={lift} />
    </>
  )
}
