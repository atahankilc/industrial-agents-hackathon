// Moving objects on the plan (access mode, backend/api/fleet.py via GET /objects, polled by the building screen): each
// object is a dot on its floor, with a heading cone when it reports a heading and its name on hover or tap; its
// trail is a faint line, its active mission's remaining line a band in the object colour (drawn like the route,
// src/dev/StoryLayer.tsx) ending at a destination badge. Positions ease from one poll to the next; nothing else
// moves.

import { useFrame, useThree } from '@react-three/fiber'
import { useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import type { FleetObject, Plan } from '../api'
import { routeRuns } from '../dev/StoryLayer'
import { ribbon, useZoomStep } from './bands'
import { toScene } from './geometry'
import type { PlanPalette } from './palette'

const PATH_Y = 0.045 // just under the Guide's route band
const MISSION_PX = 5
const CASING_PX = 9
const TRAIL_OPACITY = 0.4
const OTHER_FLOOR_OPACITY = 0.35
const EASE_SECONDS = 0.35 // a poll's new position is reached in about this long
const JUMP_M = 15 // further than this between polls: no easing, it was moved

type Lift = (index: number) => number

/** The mission line from the point nearest the object's position on, so only the part still ahead is drawn. */
function remaining(line: [number, number, number][], at: { x: number; y: number; floor: number | null } | null): [number, number, number][] {
  if (!at || at.floor === null || line.length < 2) return line
  let best = { index: -1, t: 0, distance: Infinity }
  for (let i = 0; i + 1 < line.length; i++) {
    const [ax, ay, af] = line[i]
    const [bx, by, bf] = line[i + 1]
    if (af !== at.floor || bf !== at.floor) continue
    const dx = bx - ax
    const dy = by - ay
    const length2 = dx * dx + dy * dy
    const t = length2 ? Math.max(0, Math.min(1, ((at.x - ax) * dx + (at.y - ay) * dy) / length2)) : 0
    const distance = Math.hypot(ax + dx * t - at.x, ay + dy * t - at.y)
    if (distance < best.distance) best = { index: i, t, distance }
  }
  if (best.index < 0) return line
  const [ax, ay, floor] = line[best.index]
  const [bx, by] = line[best.index + 1]
  return [[ax + (bx - ax) * best.t, ay + (by - ay) * best.t, floor], ...line.slice(best.index + 1)]
}

const activeLine = (item: FleetObject) =>
  item.mission?.status === 'active' && item.mission.line?.length ? remaining(item.mission.line, item.position) : null

/** Inside the canvas: trails, mission bands, and the tracker that places the DOM markers each frame. */
export function ObjectsLayer({ plan, objects, palette, shown, floor, stacked, lift, elements }: {
  plan: Plan
  objects: FleetObject[]
  palette: PlanPalette
  shown: number[]
  floor: number
  stacked: boolean
  lift: Lift
  elements: React.RefObject<Map<string, HTMLElement>>
}) {
  const zoom = useZoomStep()
  const key = shown.join(',')
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const floors = useMemo(() => shown, [key]) // a new array every render upstream; same floors = same drawing
  const here = useMemo(() => (stacked ? floors : [floor]), [stacked, floors, floor])

  const drawn = useMemo(() => {
    const items: { floor: number; object: THREE.Object3D }[] = []
    for (const item of objects) {
      // trail: one faint line per floor visited
      let run: [number, number][] = []
      let runFloor: number | null = null
      const flush = () => {
        if (runFloor !== null && run.length > 1 && here.includes(runFloor)) {
          const geometry = new THREE.BufferGeometry().setFromPoints(run.map(([x, y]) => {
            const [X, Z] = toScene(plan, x, y)
            return new THREE.Vector3(X, PATH_Y - 0.01, Z)
          }))
          items.push({ floor: runFloor, object: new THREE.Line(geometry, new THREE.LineBasicMaterial({ color: palette.object, transparent: true, opacity: TRAIL_OPACITY, depthWrite: false })) })
        }
        run = []
      }
      for (const [x, y, trailFloor] of item.trail) {
        if (trailFloor !== runFloor) {
          flush()
          runFloor = trailFloor
        }
        run.push([x, y])
      }
      flush()
      // the mission still ahead, cased like the route
      const line = activeLine(item)
      for (const missionRun of line ? routeRuns(line) : []) {
        if (!floors.includes(missionRun.floor) || missionRun.points.length < 2) continue
        const points = missionRun.points.map(([x, y]) => toScene(plan, x, y))
        const opacity = stacked || missionRun.floor === floor ? 1 : OTHER_FLOOR_OPACITY
        const depthTest = stacked || missionRun.floor !== floor
        const casing = new THREE.MeshBasicMaterial({ color: palette.halo, transparent: true, opacity, depthWrite: false, depthTest, side: THREE.DoubleSide })
        const band = new THREE.MeshBasicMaterial({ color: palette.object, transparent: true, opacity, depthWrite: false, depthTest, side: THREE.DoubleSide })
        const casingMesh = new THREE.Mesh(ribbon(points, CASING_PX / zoom, PATH_Y - 0.004), casing)
        const bandMesh = new THREE.Mesh(ribbon(points, MISSION_PX / zoom, PATH_Y), band)
        casingMesh.renderOrder = 5
        bandMesh.renderOrder = 6
        items.push({ floor: missionRun.floor, object: casingMesh }, { floor: missionRun.floor, object: bandMesh })
      }
    }
    return items
  }, [plan, objects, palette.object, palette.halo, floors, here, floor, stacked, zoom])
  useEffect(() => () => drawn.forEach(({ object }) => {
    const item = object as THREE.Mesh
    item.geometry.dispose()
    ;(item.material as THREE.Material).dispose()
  }), [drawn])

  return (
    <>
      {drawn.map(({ floor: at, object }, index) => (
        <group key={index} position={[0, lift(at), 0]}>
          <primitive object={object} />
        </group>
      ))}
      <ObjectTracker plan={plan} objects={objects} floors={here} lift={lift} elements={elements} />
    </>
  )
}

type Shown = { x: number; y: number; floor: number }

/** Places each object's marker (and its destination badge) on screen every frame, easing towards the last poll. */
function ObjectTracker({ plan, objects, floors, lift, elements }: {
  plan: Plan
  objects: FleetObject[]
  floors: number[]
  lift: Lift
  elements: React.RefObject<Map<string, HTMLElement>>
}) {
  const { camera, size, invalidate } = useThree()
  const at = useRef(new Map<string, Shown>())
  const point = useMemo(() => new THREE.Vector3(), [])
  const toScreen = (x: number, y: number, floor: number) => {
    const [X, Z] = toScene(plan, x, y)
    point.set(X, lift(floor) + PATH_Y, Z).project(camera)
    return [((point.x + 1) / 2) * size.width, ((1 - point.y) / 2) * size.height] as const
  }
  const place = (node: HTMLElement, x: number, y: number, floor: number) => {
    const [sx, sy] = toScreen(x, y, floor)
    node.style.transform = `translate(${sx}px, ${sy}px)`
    node.style.visibility = floors.includes(floor) && sx > -40 && sy > -40 && sx < size.width + 40 && sy < size.height + 40 ? 'visible' : 'hidden'
    return [sx, sy] as const
  }

  useFrame((_, delta) => {
    let moving = false
    const keep = Math.exp(-Math.min(delta, 0.1) / EASE_SECONDS)
    for (const item of objects) {
      const node = elements.current.get(item.id)
      const target = item.position
      if (!node || !target || target.floor === null) continue
      let shown = at.current.get(item.id)
      if (!shown || shown.floor !== target.floor || Math.hypot(shown.x - target.x, shown.y - target.y) > JUMP_M) {
        shown = { x: target.x, y: target.y, floor: target.floor }
      } else {
        shown = { x: target.x + (shown.x - target.x) * keep, y: target.y + (shown.y - target.y) * keep, floor: target.floor }
        if (Math.hypot(shown.x - target.x, shown.y - target.y) > 0.01) moving = true
        else shown = { x: target.x, y: target.y, floor: target.floor }
      }
      at.current.set(item.id, shown)
      const [sx, sy] = place(node, shown.x, shown.y, shown.floor)
      if (target.heading_deg !== null && target.heading_deg !== undefined) {
        // the cone points along the reported heading (plan frame: degrees from east, counter-clockwise), as seen on screen
        const radians = (target.heading_deg * Math.PI) / 180
        const [ax, ay] = toScreen(shown.x + Math.cos(radians), shown.y + Math.sin(radians), shown.floor)
        node.style.setProperty('--heading', `${Math.atan2(ay - sy, ax - sx) + Math.PI / 2}rad`)
      }
    }
    for (const item of objects) {
      const node = elements.current.get(`${item.id}:to`)
      const line = item.mission?.line
      if (!node || !line?.length) continue
      const [x, y, floor] = line[line.length - 1]
      place(node, x, y, floor)
    }
    if (moving) invalidate()
  })
  useEffect(() => invalidate(), [objects, floors, invalidate])
  return null
}

/** DOM markers over the canvas: the objects (tap or hover for the name) and their destinations. */
export function ObjectMarkers({ objects, palette, elements }: { objects: FleetObject[]; palette: PlanPalette; elements: React.RefObject<Map<string, HTMLElement>> }) {
  const [open, setOpen] = useState<string | null>(null)
  const ref = (key: string) => (node: HTMLElement | null) => {
    if (node) elements.current.set(key, node)
    else elements.current.delete(key)
  }
  const stop = (event: React.PointerEvent) => event.stopPropagation()
  return (
    <div className="object-markers" style={{ '--object': palette.object } as React.CSSProperties}>
      {objects.map((item) =>
        item.position && item.position.floor !== null ? (
          <div key={item.id} ref={ref(item.id)} className={`object-marker${open === item.id ? ' open' : ''}`}>
            {item.position.heading_deg !== null && item.position.heading_deg !== undefined && <b aria-hidden="true" />}
            <button type="button" onPointerDown={stop} onPointerUp={stop} onClick={() => setOpen((id) => (id === item.id ? null : item.id))} aria-label={item.name}>
              <em />
            </button>
            <span>
              {item.name}
              {item.mission?.status === 'active' && <small> → {item.mission.to.name}</small>}
            </span>
          </div>
        ) : null,
      )}
      {objects.map((item) =>
        item.mission?.status === 'active' && item.mission.line?.length ? (
          <div key={`${item.id}:to`} ref={ref(`${item.id}:to`)} className="object-marker to">
            <i aria-hidden="true" />
            <span>{item.mission.to.name}</span>
          </div>
        ) : null,
      )}
    </div>
  )
}
