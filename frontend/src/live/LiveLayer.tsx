// The living building on the plan (backend/api/live/ via GET /live, polled by the building screen): each connected
// thing is its real footprint on the floor — violet while it moves, orange when it stands and cuts a walkway (with
// the no-pass zone routing uses around it: the footprint grown by half the walker's clearance), grey when it stands
// out of the way — plus a DOM marker with its kind's icon. Behind it, its trail: the last 50 m of reported positions,
// fading out with age; ahead of a moving one, a short dashed line where it drives next. A cleaning robot's wet floor
// is a pale blue patch. Markers glide from one report to the next over the report interval and ping once per report,
// so a BLE tag (every 10 s) visibly reports less often than a forklift's telematics (every second).

import { useFrame, useThree } from '@react-three/fiber'
import { Radio } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import type { LiveSnapshot, Plan } from '../api'
import { ribbon, useZoomStep } from '../plan/bands'
import { toScene } from '../plan/geometry'
import type { PlanPalette } from '../plan/palette'
import { ago, KIND_ICON, stateLabel, tone } from './kinds'

const TRAIL_Y = 0.04
const FOOT_Y = 0.07
const FOOT_H = 0.12
const TRAIL_PX = 4
const AHEAD_PX = 2.5
const TRAIL_OPACITY = 0.6
const WET_OPACITY = 0.2
const ZONE_OPACITY = 0.16
const GLIDE_MAX_S = 2.2 // a report is reached over its interval, at most this long
const JUMP_M = 12 // further than this between reports: no glide (a lift ride, a reset)

type Lift = (index: number) => number

const fadeVertex = `
attribute float along;
varying float vAlong;
void main() {
  vAlong = along;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}`
const trailFragment = `
uniform vec3 colour;
uniform float total;
uniform float opacity;
varying float vAlong;
void main() {
  float t = clamp(vAlong / max(total, 0.001), 0.0, 1.0);
  gl_FragColor = vec4(colour, opacity * t * t);
}`
const dashFragment = `
uniform vec3 colour;
uniform float opacity;
uniform float dash;
varying float vAlong;
void main() {
  if (fract(vAlong / dash) > 0.55) discard;
  gl_FragColor = vec4(colour, opacity);
}`

/** Inside the canvas: trails, ahead lines, wet floors and footprints; places the DOM markers every frame. */
export function LiveLayer({ plan, live, palette, shown, floor, stacked, lift, elements, clearance }: {
  plan: Plan
  live: LiveSnapshot
  palette: PlanPalette
  shown: number[]
  floor: number
  stacked: boolean
  lift: Lift
  elements: React.RefObject<Map<string, HTMLElement>>
  /** the viewer's clearance (m): the no-pass zone around what blocks */
  clearance: number
}) {
  const zoom = useZoomStep()
  const key = shown.join(',')
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const floors = useMemo(() => shown, [key])
  const here = useMemo(() => (stacked ? floors : [floor]), [stacked, floors, floor])

  // lines and patches: rebuilt per poll (reports change them), cheap
  const drawn = useMemo(() => {
    const items: { floor: number; object: THREE.Object3D }[] = []
    const material = (fragment: string, colour: string, uniforms: Record<string, number>) =>
      new THREE.ShaderMaterial({
        vertexShader: fadeVertex,
        fragmentShader: fragment,
        uniforms: { colour: { value: new THREE.Color(colour) }, ...Object.fromEntries(Object.entries(uniforms).map(([name, value]) => [name, { value }])) },
        transparent: true,
        depthWrite: false,
        side: THREE.DoubleSide,
      })
    const runs = (points: [number, number, number | null][]) => {
      const out: { floor: number; points: [number, number][] }[] = []
      for (const [x, y, at] of points) {
        if (at === null) continue
        const last = out[out.length - 1]
        if (last && last.floor === at) last.points.push(toScene(plan, x, y))
        else out.push({ floor: at, points: [toScene(plan, x, y)] })
      }
      return out.filter((run) => run.points.length > 1 && here.includes(run.floor))
    }
    for (const item of live.devices) {
      const colour = item.moving ? palette.object : item.blocking ? palette.liveBlock : palette.liveIdle
      for (const run of runs(item.trail)) {
        const geometry = ribbon(run.points, TRAIL_PX / zoom, TRAIL_Y)
        const total = run.points.slice(1).reduce((sum, [X, Z], i) => sum + Math.hypot(X - run.points[i][0], Z - run.points[i][1]), 0)
        const mesh = new THREE.Mesh(geometry, material(trailFragment, colour, { total, opacity: TRAIL_OPACITY }))
        mesh.renderOrder = 3
        items.push({ floor: run.floor, object: mesh })
      }
      for (const run of item.moving ? runs(item.ahead) : []) {
        const mesh = new THREE.Mesh(ribbon(run.points, AHEAD_PX / zoom, TRAIL_Y + 0.002), material(dashFragment, colour, { opacity: 0.75, dash: 0.9 }))
        mesh.renderOrder = 3
        items.push({ floor: run.floor, object: mesh })
      }
    }
    for (const hazard of live.hazards) {
      if (hazard.floor === null || !here.includes(hazard.floor) || hazard.polygon.length < 3) continue
      const shape = new THREE.Shape(hazard.polygon.map(([x, y]) => {
        const [X, Z] = toScene(plan, x, y)
        return new THREE.Vector2(X, -Z)
      }))
      const geometry = new THREE.ShapeGeometry(shape)
      geometry.rotateX(-Math.PI / 2)
      geometry.translate(0, TRAIL_Y - 0.008, 0)
      const mesh = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({ color: palette.liveWet, transparent: true, opacity: WET_OPACITY, depthWrite: false, side: THREE.DoubleSide }))
      mesh.renderOrder = 2
      items.push({ floor: hazard.floor, object: mesh })
    }
    return items
  }, [plan, live, palette.object, palette.liveBlock, palette.liveIdle, palette.liveWet, here, zoom])
  useEffect(() => () => drawn.forEach(({ object }) => {
    const mesh = object as THREE.Mesh
    mesh.geometry.dispose()
    ;(mesh.material as THREE.Material).dispose()
  }), [drawn])

  return (
    <>
      {drawn.map(({ floor: at, object }, index) => (
        <group key={index} position={[0, lift(at), 0]}>
          <primitive object={object} />
        </group>
      ))}
      <Footprints plan={plan} live={live} palette={palette} floors={here} lift={lift} elements={elements} clearance={clearance} />
    </>
  )
}

type Glide = { from: [number, number, number]; to: [number, number, number]; floor: number; started: number; seconds: number; at: number }

/** The footprints, gliding from report to report, and the DOM markers placed over them each frame. */
function Footprints({ plan, live, palette, floors, lift, elements, clearance }: {
  plan: Plan
  live: LiveSnapshot
  palette: PlanPalette
  floors: number[]
  lift: Lift
  elements: React.RefObject<Map<string, HTMLElement>>
  clearance: number
}) {
  const { camera, size, invalidate } = useThree()
  const glides = useRef(new Map<string, Glide>())
  const groups = useRef(new Map<string, THREE.Group>())
  const point = useMemo(() => new THREE.Vector3(), [])
  const clock = useRef(0)

  // a new report: glide from where the marker is now to it, over the report interval
  useEffect(() => {
    const now = clock.current
    const seen = new Set<string>()
    for (const item of live.devices) {
      const { x, y, floor, heading_deg } = item.position
      if (floor === null) continue
      seen.add(item.id)
      const heading = ((heading_deg ?? 0) * Math.PI) / 180
      const old = glides.current.get(item.id)
      const target: [number, number, number] = [x, y, heading]
      if (old && old.to[0] === x && old.to[1] === y && old.floor === floor) continue
      const current = old ? position(old, now) : target
      const jump = !old || old.floor !== floor || Math.hypot(current[0] - x, current[1] - y) > JUMP_M
      const seconds = item.moving ? Math.min(GLIDE_MAX_S, item.report_every_s) / Math.max(0.25, live.speed) : 0.6
      glides.current.set(item.id, { from: jump ? target : current, to: target, floor, started: now, seconds: jump ? 0 : seconds, at: item.reported_at })
    }
    for (const id of [...glides.current.keys()]) if (!seen.has(id)) glides.current.delete(id)
    invalidate()
  }, [live, invalidate])

  const toScreen = (x: number, y: number, floor: number) => {
    const [X, Z] = toScene(plan, x, y)
    point.set(X, lift(floor) + FOOT_Y, Z).project(camera)
    return [((point.x + 1) / 2) * size.width, ((1 - point.y) / 2) * size.height] as const
  }

  useFrame((_, delta) => {
    clock.current += Math.min(delta, 0.1)
    let moving = false
    for (const item of live.devices) {
      const glide = glides.current.get(item.id)
      if (!glide) continue
      const [x, y, heading] = position(glide, clock.current)
      if (clock.current - glide.started < glide.seconds) moving = true
      const visible = floors.includes(glide.floor)
      const group = groups.current.get(item.id)
      if (group) {
        const [X, Z] = toScene(plan, x, y)
        group.position.set(X, lift(glide.floor), Z)
        group.rotation.set(0, heading, 0)
        group.visible = visible
      }
      const node = elements.current.get(item.id)
      if (node) {
        const [sx, sy] = toScreen(x, y, glide.floor)
        node.style.transform = `translate(${sx}px, ${sy}px)`
        node.style.visibility = visible && sx > -40 && sy > -40 && sx < size.width + 40 && sy < size.height + 40 ? 'visible' : 'hidden'
      }
    }
    if (moving) invalidate()
  })

  return (
    <>
      {live.devices.map((item) => {
        const colour = item.moving ? palette.object : item.blocking ? palette.liveBlock : palette.liveIdle
        const { length_m: length, width_m: width } = item.footprint
        return (
          <group key={item.id} ref={(node) => (node ? groups.current.set(item.id, node) : groups.current.delete(item.id))} visible={false}>
            {item.blocking && (
              <mesh position={[0, FOOT_Y - 0.03, 0]} rotation={[-Math.PI / 2, 0, 0]} renderOrder={4}>
                <planeGeometry args={[length + clearance, width + clearance]} />
                <meshBasicMaterial color={palette.liveBlock} transparent opacity={ZONE_OPACITY} depthWrite={false} />
              </mesh>
            )}
            <mesh position={[0, FOOT_Y + FOOT_H / 2, 0]} renderOrder={5}>
              <boxGeometry args={[length, FOOT_H, width]} />
              <meshBasicMaterial color={colour} transparent opacity={item.moving ? 0.9 : 0.85} depthWrite={false} />
            </mesh>
          </group>
        )
      })}
    </>
  )
}

function position(glide: Glide, now: number): [number, number, number] {
  const t = glide.seconds <= 0 ? 1 : Math.min(1, (now - glide.started) / glide.seconds)
  const turn = Math.atan2(Math.sin(glide.to[2] - glide.from[2]), Math.cos(glide.to[2] - glide.from[2]))
  return [glide.from[0] + (glide.to[0] - glide.from[0]) * t, glide.from[1] + (glide.to[1] - glide.from[1]) * t, glide.from[2] + turn * t]
}

/** DOM markers over the canvas: the kind's icon in its tone; tap or hover for what it is and what it reports. */
export function LiveMarkers({ live, elements, palette, focus, onFocus }: {
  live: LiveSnapshot
  elements: React.RefObject<Map<string, HTMLElement>>
  palette: PlanPalette
  focus: string | null
  onFocus: (id: string | null) => void
}) {
  const [hover, setHover] = useState<string | null>(null)
  const ref = (key: string) => (node: HTMLElement | null) => {
    if (node) elements.current.set(key, node)
    else elements.current.delete(key)
  }
  const stop = (event: React.PointerEvent) => event.stopPropagation()
  return (
    <div className="live-markers" style={{ '--live-moving': palette.object, '--live-block': palette.liveBlock, '--live-idle': palette.liveIdle } as React.CSSProperties}>
      {live.devices.map((item) => {
        const Icon = KIND_ICON[item.kind] ?? Radio
        const open = focus === item.id || hover === item.id
        return (
          <div key={item.id} ref={ref(item.id)} className={`live-marker ${tone(item)}${open ? ' open' : ''}${focus === item.id ? ' focused' : ''}`}>
            {/* one ping per report: keyed by the report, so it plays again when the next one comes in */}
            <i key={item.reported_at} className="ping" aria-hidden="true" />
            <button
              type="button"
              onPointerDown={stop}
              onPointerUp={stop}
              onPointerEnter={() => setHover(item.id)}
              onPointerLeave={() => setHover((id) => (id === item.id ? null : id))}
              onClick={() => onFocus(focus === item.id ? null : item.id)}
              aria-label={`${item.name}, ${stateLabel(item.state)}`}
            >
              <Icon size={14} strokeWidth={2.2} />
            </button>
            {open && (
              <span className="live-card">
                <b>{item.name}</b>
                <small>
                  {stateLabel(item.state)}
                  {item.to ? ` → ${item.to}` : item.position.space ? ` · ${item.position.space}` : ''}
                </small>
                {item.blocking && <em>Blocks {item.blocking.space} — routes go round</em>}
                <small className="link">
                  {item.link} · every {item.report_every_s < 1.5 ? '1 s' : `${Math.round(item.report_every_s)} s`} · {ago(item.reported_ago_s)}
                  {item.source === 'sim' ? ' · simulated' : ''}
                </small>
              </span>
            )}
          </div>
        )
      })}
    </div>
  )
}
