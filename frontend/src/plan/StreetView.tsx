// Street view: down from the plan to eye level on one floor, where you stand. The camera eases down from above the
// spot to a standing eye height and faces the way given (along the route, else the way the plan looked). Drag to
// look round, tap the floor to walk there, arrow keys or WASD to walk and turn, wheel to zoom; Esc or the back
// button goes up to the plan again, which is where it was left. On a phone the compass button makes the view
// follow the phone: turn round and it turns, hold the phone up or down and it looks up or down (./compass.ts). Walls stand at the floor's storey height (from the
// floors' elevations) with no ceiling over them; the route runs on the floor as a band with chevrons. Its own
// canvas over the plan's, rendering on demand like the plan.

import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { ArrowLeft, Compass } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import type { Plan } from '../api'
import { routeMaterial, routeRuns } from '../dev/StoryLayer'
import { ribbon } from './bands'
import { askForCompass, compassLikely, shortest, turnFor, watchCompass, type Facing } from './compass'
import { contains, fromScene, toScene } from './geometry'
import type { Insets } from './PlanView'
import type { PlanPalette } from './palette'

const EYE_M = 1.6 // UNVERIFIED: a standing adult's eye height
const FROM_M = 24 // where the descent starts, above the spot
const DESCENT_SECONDS = 1.2
const LOOK_RAD_PER_PX = 0.005
const MIN_PITCH = -1.2
const MAX_PITCH = 0.9
const START_PITCH = -0.12 // a little down, so the floor ahead (and the route on it) is in view
const WALK_MPS = 2.4 // arrow keys; a tap walks there in WALK_SECONDS at most
const WALK_SECONDS = 1.4
const TURN_RAD_PER_S = 1.6
const TAP_SLOP_PX = 8
const FOV = 70
const MIN_FOV = 35
const MAX_FOV = 85
const ROUTE_M = 0.7 // the route band's width on the floor
const ROUTE_Y = 0.02
const FOLLOW_RATE = 10 // how fast the view catches up with the phone (per second; readings are noisy)
const COMPASS_WAIT_MS = 2000 // no reading by then: this device has no compass
const ROUTE_PIXEL_M = 0.03 // the route shader's "pixel" in metres: chevrons 0.9 m apart, as wide as the band allows

/** Where street view stands: a point in plan metres on a floor, and the way it first faces (camera yaw, radians;
 * 0 looks along scene -Z, the plan's north). */
export type Street = { at: [number, number]; floor: number; yaw: number }

type Props = {
  plan: Plan
  palette: PlanPalette
  street: Street
  insets: Insets
  /** the route's polyline ([x, y, floor], plan metres), drawn on this floor */
  route?: [number, number, number][] | null
  /** start following the phone's compass (it was on over the plan) */
  compass?: boolean
  /** the floor's model (lights and FloorModel, built at storey height by PlanView) */
  children: React.ReactNode
  onClose: () => void
}

export function StreetView({ plan, palette, street, insets, route, compass = false, children, onClose }: Props) {
  const [room, setRoom] = useState(() => roomAt(plan, street.floor, street.at))
  const [following, setFollowing] = useState(compass)
  const [noCompass, setNoCompass] = useState(false)
  const canFollow = useMemo(compassLikely, [])
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === 'Escape' && !typing(event) && onCloseRef.current()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
  const stop = (event: React.SyntheticEvent) => event.stopPropagation() // the plan under it must not take these
  return (
    <div className="street" onPointerDown={stop} onPointerMove={stop} onPointerUp={stop} onClick={stop} onWheel={stop} onContextMenu={(event) => event.preventDefault()}>
      <Canvas flat frameloop="demand" dpr={[1, 2]} gl={{ antialias: true }} camera={{ fov: FOV, near: 0.05, far: 800 }} onCreated={({ gl }) => gl.setClearColor(palette.ground)}>
        {children}
        {route && <StreetRoute plan={plan} line={route} floor={street.floor} palette={palette} />}
        <Walker plan={plan} street={street} following={following} onRoom={setRoom} onNoCompass={() => {
          setFollowing(false)
          setNoCompass(true)
        }} />
      </Canvas>
      <div className="street-bar" style={{ top: insets.top + 8, left: insets.left + 16, right: insets.right + 16 }}>
        <button type="button" className="street-back" onClick={onClose} aria-label="Back to the plan" title="Back to the plan · Esc">
          <ArrowLeft size={18} aria-hidden="true" />
          <span>Plan</span>
        </button>
        <p className="street-room" role="status">
          {room ? room : 'Not in a room'}
          <small>{plan.floors[street.floor]?.name ?? ''}</small>
        </p>
        {canFollow && (
          <button
            type="button"
            className={`street-compass${following ? ' on' : ''}`}
            aria-pressed={following}
            aria-label={following ? 'Stop following the phone' : 'Follow the phone: turn round to look round'}
            title={noCompass ? 'No compass reading on this device' : following ? 'Following the phone · tap to stop' : 'Follow the phone'}
            onClick={async () => {
              if (following) return setFollowing(false)
              setNoCompass(false)
              if (await askForCompass()) setFollowing(true)
              else setNoCompass(true)
            }}
          >
            <Compass size={18} aria-hidden="true" />
          </button>
        )}
      </div>
      {noCompass && (
        <p className="street-hint shown" style={{ bottom: insets.bottom + 16 }} role="status">
          No compass here: drag to look round
        </p>
      )}
      <p className="street-hint" style={{ bottom: insets.bottom + 16 }}>
        {following ? 'Turn round to look round · tap the floor to walk' : canFollow ? 'Drag to look · tap the floor to walk' : 'Drag to look · tap the floor to walk · arrows to move'}
      </p>
    </div>
  )
}

/** The smallest room on the floor that the point (plan metres) is in, by name. */
function roomAt(plan: Plan, floor: number, [x, y]: [number, number]): string | null {
  let best: { name: string; area: number } | null = null
  for (const space of plan.spaces) {
    if (space.floor !== floor || !contains(space.polygon, x, y)) continue
    if (!best || space.area_m2 < best.area) best = { name: space.name, area: space.area_m2 }
  }
  return best?.name ?? null
}

const typing = (event: KeyboardEvent) => {
  const target = event.target as HTMLElement | null
  return !!target && (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName))
}

type Walk = { from: THREE.Vector2; to: THREE.Vector2; t: number; seconds: number }

/** The camera: the descent, looking round (drag), walking (tap on the floor, keys) and zooming (wheel). */
function Walker({ plan, street, following, onRoom, onNoCompass }: {
  plan: Plan
  street: Street
  /** the phone's compass turns the view (and its tilt tilts it); dragging and turning keys then do not */
  following: boolean
  onRoom: (room: string | null) => void
  onNoCompass: () => void
}) {
  const camera = useThree((state) => state.camera) as THREE.PerspectiveCamera
  const gl = useThree((state) => state.gl)
  const scene = useThree((state) => state.scene)
  const invalidate = useThree((state) => state.invalidate)
  const state = useMemo(() => {
    const [X, Z] = toScene(plan, ...street.at)
    return { at: new THREE.Vector2(X, Z), yaw: street.yaw, pitch: START_PITCH, descent: 0, walk: null as Walk | null, keys: new Set<string>(), room: '' }
    // a new street (another spot) starts over; the plan object itself is stable while it is open
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [street])
  const onRoomRef = useRef(onRoom)
  onRoomRef.current = onRoom
  const onNoCompassRef = useRef(onNoCompass)
  onNoCompassRef.current = onNoCompass
  const facing = useRef<Facing | null>(null)
  const followingRef = useRef(following)
  followingRef.current = following

  useEffect(() => {
    facing.current = null
    if (!following) return
    let heard = false
    const stop = watchCompass((reading) => {
      heard = true
      facing.current = reading
      invalidate()
    })
    const timer = setTimeout(() => !heard && onNoCompassRef.current(), COMPASS_WAIT_MS)
    return () => {
      stop()
      clearTimeout(timer)
    }
  }, [following, invalidate])

  // can stand there: inside a room of this floor (walls between rooms are not checked, the building's outside is)
  const standable = (X: number, Z: number) => {
    const [x, y] = fromScene(plan, X, Z)
    return plan.spaces.some((space) => space.floor === street.floor && contains(space.polygon, x, y))
  }

  useEffect(() => {
    const element = gl.domElement
    let drag: { x: number; y: number; moved: boolean; id: number } | null = null
    const down = (event: PointerEvent) => {
      if (drag) return
      element.setPointerCapture(event.pointerId)
      drag = { x: event.clientX, y: event.clientY, moved: false, id: event.pointerId }
    }
    const move = (event: PointerEvent) => {
      if (!drag || event.pointerId !== drag.id) return
      const [dx, dy] = [event.clientX - drag.x, event.clientY - drag.y]
      if (!drag.moved && Math.hypot(dx, dy) < TAP_SLOP_PX) return
      if (!drag.moved) state.descent = 1 // looking round lands you at once
      drag.moved = true
      drag.x = event.clientX
      drag.y = event.clientY
      if (followingRef.current) return // the phone turns the view
      // the scene follows the finger, as in a photo you drag round
      state.yaw += dx * LOOK_RAD_PER_PX * (camera.fov / FOV)
      state.pitch = THREE.MathUtils.clamp(state.pitch + dy * LOOK_RAD_PER_PX * (camera.fov / FOV), MIN_PITCH, MAX_PITCH)
      invalidate()
    }
    const up = (event: PointerEvent) => {
      if (!drag || event.pointerId !== drag.id) return
      const tapped = !drag.moved && event.type === 'pointerup'
      drag = null
      if (!tapped) return
      const box = element.getBoundingClientRect()
      const ndc = new THREE.Vector2(((event.clientX - box.left) / box.width) * 2 - 1, -((event.clientY - box.top) / box.height) * 2 + 1)
      const ray = new THREE.Raycaster()
      ray.setFromCamera(ndc, camera)
      // the first solid thing under the tap; only the floor (a surface facing up, at floor height) is walked to
      const hit = ray.intersectObjects(scene.children, true).find((item) => item.object instanceof THREE.Mesh && item.object.visible)
      if (!hit || Math.abs(hit.point.y) > 0.1) return
      const to = new THREE.Vector2(hit.point.x, hit.point.z)
      if (!standable(to.x, to.y)) return
      state.descent = 1
      state.walk = { from: state.at.clone(), to, t: 0, seconds: Math.min(WALK_SECONDS, Math.max(0.35, state.at.distanceTo(to) / 4)) }
      invalidate()
    }
    const wheel = (event: WheelEvent) => {
      event.preventDefault()
      camera.fov = THREE.MathUtils.clamp(camera.fov * Math.exp(event.deltaY * 0.001), MIN_FOV, MAX_FOV)
      camera.updateProjectionMatrix()
      invalidate()
    }
    const KEYS = ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'w', 'a', 's', 'd']
    const keyDown = (event: KeyboardEvent) => {
      const key = event.key.length === 1 ? event.key.toLowerCase() : event.key
      if (!KEYS.includes(key) || typing(event)) return
      event.preventDefault()
      state.keys.add(key)
      state.descent = 1
      state.walk = null
      invalidate()
    }
    const keyUp = (event: KeyboardEvent) => state.keys.delete(event.key.length === 1 ? event.key.toLowerCase() : event.key)
    const blur = () => state.keys.clear()
    element.addEventListener('pointerdown', down)
    element.addEventListener('pointermove', move)
    element.addEventListener('pointerup', up)
    element.addEventListener('pointercancel', up)
    element.addEventListener('wheel', wheel, { passive: false })
    window.addEventListener('keydown', keyDown)
    window.addEventListener('keyup', keyUp)
    window.addEventListener('blur', blur)
    element.style.touchAction = 'none'
    return () => {
      element.removeEventListener('pointerdown', down)
      element.removeEventListener('pointermove', move)
      element.removeEventListener('pointerup', up)
      element.removeEventListener('pointercancel', up)
      element.removeEventListener('wheel', wheel)
      window.removeEventListener('keydown', keyDown)
      window.removeEventListener('keyup', keyUp)
      window.removeEventListener('blur', blur)
    }
    // standable reads the plan and floor, which come with the street
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gl, camera, scene, invalidate, state])

  useFrame((_, delta) => {
    // on-demand rendering: the first frame's delta is the whole idle time before it, so cap the step
    const step = Math.min(delta, 1 / 30)
    let moving = false
    const face = facing.current
    if (face) {
      // ease toward the phone: the short way round, and its tilt as the look up or down
      const k = 1 - Math.exp(-FOLLOW_RATE * step)
      const turn = shortest(state.yaw, turnFor(face.heading))
      const tilt = THREE.MathUtils.clamp(face.pitch, MIN_PITCH, MAX_PITCH) - state.pitch
      state.yaw += turn * k
      state.pitch += tilt * k
      if (Math.abs(turn) > 1e-3 || Math.abs(tilt) > 1e-3) moving = true
    }
    let height = EYE_M
    let pitch = state.pitch
    if (state.descent < 1) {
      state.descent = Math.min(1, state.descent + step / DESCENT_SECONDS)
      const k = 1 - Math.pow(1 - state.descent, 3)
      height = FROM_M + (EYE_M - FROM_M) * k
      pitch = -Math.PI / 2 + 0.01 + (state.pitch + Math.PI / 2 - 0.01) * k // from straight down to the way it faces
      moving = true
    }
    const walk = state.walk
    if (walk) {
      walk.t = Math.min(1, walk.t + step / walk.seconds)
      const k = walk.t < 0.5 ? 2 * walk.t * walk.t : 1 - Math.pow(-2 * walk.t + 2, 2) / 2
      state.at.lerpVectors(walk.from, walk.to, k)
      if (walk.t >= 1) state.walk = null
      moving = true
    }
    const { keys } = state
    if (keys.size) {
      const turn = facing.current ? 0 : (keys.has('ArrowLeft') || keys.has('a') ? 1 : 0) - (keys.has('ArrowRight') || keys.has('d') ? 1 : 0)
      const ahead = (keys.has('ArrowUp') || keys.has('w') ? 1 : 0) - (keys.has('ArrowDown') || keys.has('s') ? 1 : 0)
      state.yaw += turn * TURN_RAD_PER_S * step
      if (ahead) {
        const X = state.at.x - Math.sin(state.yaw) * ahead * WALK_MPS * step
        const Z = state.at.y - Math.cos(state.yaw) * ahead * WALK_MPS * step
        if (standable(X, Z)) state.at.set(X, Z)
        else if (standable(X, state.at.y)) state.at.x = X // slide along the edge
        else if (standable(state.at.x, Z)) state.at.y = Z
      }
      moving = true
    }
    camera.position.set(state.at.x, height, state.at.y)
    camera.rotation.set(pitch, state.yaw, 0, 'YXZ')
    const room = roomAt(plan, street.floor, fromScene(plan, state.at.x, state.at.y)) ?? ''
    if (room !== state.room) {
      state.room = room
      onRoomRef.current(room || null)
    }
    if (moving) invalidate()
  })
  return null
}

/** The route's run on this floor as a band on the floor, chevrons pointing the way it goes. */
function StreetRoute({ plan, line, floor, palette }: { plan: Plan; line: [number, number, number][]; floor: number; palette: PlanPalette }) {
  const invalidate = useThree((state) => state.invalidate)
  const geometries = useMemo(
    () => routeRuns(line).filter((run) => run.floor === floor).map((run) => ({ geometry: ribbon(run.points.map(([x, y]) => toScene(plan, x, y)), ROUTE_M, ROUTE_Y), offset: run.offset })),
    [plan, line, floor],
  )
  const materials = useMemo(
    () =>
      geometries.map(({ offset }) => {
        const material = routeMaterial(palette.selectedEdge, palette.labelSoft, true)
        material.uniforms.progress.value = 1e9 // drawn in full
        material.uniforms.offset.value = offset
        material.uniforms.pixel.value = ROUTE_PIXEL_M
        material.uniforms.bandHalf.value = ROUTE_M / 2
        return material
      }),
    [geometries, palette],
  )
  useEffect(() => () => geometries.forEach(({ geometry }) => geometry.dispose()), [geometries])
  useEffect(() => () => materials.forEach((material) => material.dispose()), [materials])
  useEffect(() => invalidate(), [geometries, materials, invalidate])
  return (
    <>
      {geometries.map(({ geometry }, i) => (
        <mesh key={i} geometry={geometry} material={materials[i]} renderOrder={2} raycast={() => null} />
      ))}
    </>
  )
}
