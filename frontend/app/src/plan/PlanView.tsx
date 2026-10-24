// The plan canvas: the building as a matte clay cutaway model. One floor at a time, or every floor stacked and
// spread apart so you can see how they sit on each other (tap one to step into it). The camera tilts freely
// between isometric and straight-down (a flat plan) like a map: right-drag, Ctrl/Shift + drag or a two-finger
// drag tilts and turns, one finger or the mouse pans, pinch or wheel zooms.
// Tap a room or a piece of furniture to select it. Renders on demand only: a frame is drawn when the camera or
// the drawing changes, never in idle. Labels (rooms, or floor names when stacked) are painted on a 2D canvas over
// the WebGL one after every frame.

import { MapControls } from '@react-three/drei'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import type { MapControls as MapControlsImpl } from 'three-stdlib'
import type { Plan, PlanSpace } from '../api'
import { assetAt, paintAsset } from './furniture'
import { buildFloors, contains, fillOf, fromScene, paintSpace, toScene, WALL_CUT_M, type FloorGeometry } from './geometry'
import type { PlanPalette } from './palette'
import { Pins, PinTracker, pinsFor, type Pin } from './pins'
import type { PlanSettings } from './settings'

export type Insets = { top: number; right: number; bottom: number; left: number }
export type ViewMode = '3d' | '2d'
export type Selected = { kind: 'space' | 'asset'; id: string }
type Hit = { floor: number; selected: Selected | null }

type Props = {
  plan: Plan
  floor: number
  stacked: boolean
  palette: PlanPalette
  selected: Selected | null
  insets: Insets
  fitKey: number
  onSelect: (selected: Selected | null) => void
  onPickFloor: (floor: number) => void
  onTilt: (mode: ViewMode) => void
  /** in 3D, show every floor spread apart around the current one so none hides another */
  spread: boolean
  settings: PlanSettings
}

const FIT_MARGIN_PX = 24
const MOVE_SECONDS = 0.55
const TAP_SLOP_PX = 8
const MAX_ZOOM = 220
const CAMERA_DISTANCE = 400
const FLAT_POLAR = 0.0001
const MAX_POLAR = 1.2
const FLAT_BELOW = 0.14 // a tilt this small snaps to straight-down when the gesture ends
const STACK_GAP_M = 5.5
const SLIDE_SECONDS = 0.5
const GROUND_BELOW_M = 0.36 // just under the slab edge
const TILTED = { polar: 0.98, azimuth: Math.PI / 4 } // ~34° above the horizon, looking from the south-east corner

const floorLift = (index: number) => index * STACK_GAP_M
export function PlanView(props: Props) {
  const { plan, floor, stacked, palette, selected, insets, fitKey, onSelect, onPickFloor, onTilt, spread, settings } = props
  const labels = useRef<HTMLCanvasElement>(null)
  const { wallHeight, colours } = settings
  const floors = useMemo(() => buildFloors(plan, palette, { wallHeight, colours }), [plan, palette, wallHeight, colours])
  const [hovered, setHovered] = useState<string | null>(null)
  const pinList = useMemo(() => (settings.pins && !stacked ? pinsFor(plan, floor) : []), [settings.pins, stacked, plan, floor])
  const pinElements = useRef(new Map<string, HTMLElement>())
  const pinnedSpaces = useMemo(() => new Set(pinList.map((pin) => pin.space).filter((id): id is string => Boolean(id))), [pinList])
  // Single-floor 3D view: the current floor (at y = 0) plus the floors below it at their real height, nearly
  // transparent, for context; floors above are not drawn at all. "All floors" is a plain fixed-gap stack.
  // above and below that none ever covers it on screen. The "all floors" view keeps the plain fixed-gap stack.
  const spreading = spread && !stacked
  const elevation = useCallback((index: number) => plan.floors[index]?.elevation_m ?? 0, [plan])
  const lift = useCallback(
    (index: number) => (stacked ? floorLift(index) : spreading ? elevation(index) - elevation(floor) : 0),
    [stacked, spreading, floor, elevation],
  )
  useEffect(() => () => floors.forEach(disposeFloor), [floors])
  const down = useRef<{ x: number; y: number } | null>(null)
  const pick = useRef<(x: number, y: number) => Hit | null>(() => null)
  const shown = stacked ? [...floors.keys()] : spreading ? [...floors.keys()].filter((i) => i <= floor) : [floor]

  return (
    <div
      className="plan"
      onContextMenu={(event) => event.preventDefault()}
      onPointerDown={(event) => (down.current = { x: event.clientX, y: event.clientY })}
      onPointerMove={(event) => {
        if (!settings.hover || stacked || event.pointerType !== 'mouse' || event.buttons) return
        const rect = event.currentTarget.getBoundingClientRect()
        const hit = pick.current(event.clientX - rect.left, event.clientY - rect.top)
        const id = hit?.selected?.kind === 'space' ? hit.selected.id : null
        if (id !== hovered) setHovered(id)
      }}
      onPointerLeave={() => setHovered(null)}
      style={settings.hover && hovered ? { cursor: 'pointer' } : undefined}
      onPointerUp={(event) => {
        const start = down.current
        down.current = null
        if (!start || event.button !== 0 || Math.hypot(event.clientX - start.x, event.clientY - start.y) > TAP_SLOP_PX) return
        const rect = event.currentTarget.getBoundingClientRect()
        const hit = pick.current(event.clientX - rect.left, event.clientY - rect.top)
        // a tap on another floor steps onto it; on the current floor it selects what is there
        if (hit && (stacked || hit.floor !== floor)) onPickFloor(hit.floor)
        else onSelect(hit?.selected ?? null)
      }}
    >
      <Canvas
        orthographic
        flat
        shadows
        frameloop="demand"
        dpr={[1, 2]}
        gl={{ antialias: true, alpha: true }}
        camera={{ position: [0, CAMERA_DISTANCE, 0.001], zoom: 8, near: 1, far: CAMERA_DISTANCE * 3 }}
        onCreated={({ gl }) => gl.setClearColor(0x000000, 0)}
      >
        <Lights plan={plan} floors={shown} palette={palette} lift={lift} />
        <Slide floor={stacked ? -1 : floor} heightOf={spreading ? elevation : floorLift}>
          <Ground plan={plan} palette={palette} y={(spreading || stacked ? lift(groundIndex(plan)) : 0) - GROUND_BELOW_M} />
          {shown.map((index) => (
            <group key={index} position={[0, lift(index), 0]}>
              <FloorModel
                geometry={floors[index]}
                palette={palette}
                floor={index}
                furniture={settings.furniture === 'full'}
                faded={spreading && index < floor}
              />
            </group>
          ))}
          {!stacked && <Selection plan={plan} selected={selected} palette={palette} floors={floors} colours={colours} />}
          {!stacked && settings.hover && hovered && hovered !== selected?.id && (
            <Hover plan={plan} id={hovered} palette={palette} floors={floors} colours={colours} />
          )}
        </Slide>
        <Rig plan={plan} floor={floor} floors={shown} stacked={stacked} insets={insets} fitKey={fitKey} onTilt={onTilt} />
        <Picker plan={plan} floors={stacked ? shown : shown.filter((i) => i <= floor)} lift={lift} stacked={stacked} geometries={floors} pick={pick} />
        <LabelPainter plan={plan} floor={floor} stacked={stacked} tags={stacked} lift={lift} palette={palette} canvas={labels} selected={selected} skip={pinnedSpaces} />
        <PinTracker plan={plan} pins={pinList} elements={pinElements} />
      </Canvas>
      <canvas ref={labels} className="plan-labels" aria-hidden="true" />
      <Pins pins={pinList} elements={pinElements} onPick={(pin: Pin) => pin.space && onSelect({ kind: 'space', id: pin.space })} />
    </div>
  )
}

function disposeFloor(floor: FloorGeometry) {
  for (const geometry of [floor.fills, floor.slab, floor.walls, floor.shade, floor.lines, floor.outline, floor.doors, floor.wallEdges, floor.furnitureEdges, floor.contact, floor.furniture]) geometry.dispose()
}

const groundIndex = (plan: Plan) => Math.max(0, plan.floors.findIndex((item) => item.level === 0))

/** Everything drawn relative to the current floor. When the floor changes, the whole stack starts where it was
 * and slides into place, so you see yourself going up or down. */
function Slide({ floor, heightOf, children }: { floor: number; heightOf: (index: number) => number; children: React.ReactNode }) {
  const group = useRef<THREE.Group>(null)
  const previous = useRef(floor)
  const invalidate = useThree((state) => state.invalidate)
  useLayoutEffect(() => {
    if (group.current && floor >= 0 && previous.current >= 0 && floor !== previous.current) {
      group.current.position.y = heightOf(floor) - heightOf(previous.current)
      invalidate()
    }
    previous.current = floor
  }, [floor, heightOf, invalidate])
  useFrame((_, delta) => {
    const node = group.current
    if (!node || node.position.y === 0) return
    // exponential ease-out, frame-rate independent; capped step because on-demand frames can be far apart
    const keep = Math.pow(0.002, Math.min(delta, 1 / 30) / SLIDE_SECONDS)
    node.position.y = Math.abs(node.position.y) < 0.01 ? 0 : node.position.y * keep
    invalidate()
  })
  return <group ref={group}>{children}</group>
}

/** A wide ground plane with a fine grid that belongs to the world, so it turns, tilts and pans with the building
 * and fades out towards the horizon. */
function Ground({ plan, palette, y }: { plan: Plan; palette: PlanPalette; y: number }) {
  const centre = useMemo(() => floorBox(plan, plan.floors.map((_, i) => i)).getCenter(new THREE.Vector2()), [plan])
  const material = useMemo(
    () =>
      new THREE.ShaderMaterial({
        transparent: true,
        depthWrite: false,
        uniforms: {
          color: { value: new THREE.Color(palette.grid) },
          strength: { value: palette.gridAlpha },
          centre: { value: new THREE.Vector2(centre.x, centre.y) },
        },
        vertexShader: `varying vec2 vWorld;
          void main() { vec4 w = modelMatrix * vec4(position, 1.0); vWorld = w.xz; gl_Position = projectionMatrix * viewMatrix * w; }`,
        fragmentShader: `uniform vec3 color; uniform float strength; uniform vec2 centre; varying vec2 vWorld;
          float lines(vec2 p, float step) {
            vec2 g = abs(fract(p / step - 0.5) - 0.5) / fwidth(p / step);
            return 1.0 - min(min(g.x, g.y), 1.0);
          }
          void main() {
            float fine = lines(vWorld, 2.0) * 0.55;
            float bold = lines(vWorld, 10.0);
            float fade = 1.0 - smoothstep(60.0, 220.0, distance(vWorld, centre));
            gl_FragColor = vec4(color, max(fine, bold) * strength * fade);
          }`,
      }),
    [palette.grid, palette.gridAlpha, centre],
  )
  useEffect(() => () => material.dispose(), [material])
  return (
    <mesh position={[centre.x, y, centre.y]} rotation={[-Math.PI / 2, 0, 0]} material={material} renderOrder={-2}>
      <planeGeometry args={[600, 600]} />
    </mesh>
  )
}

function floorBox(plan: Plan, floors: number[]) {
  const box = new THREE.Box2()
  for (const space of plan.spaces) {
    if (!floors.includes(space.floor)) continue
    for (const [x, y] of space.polygon) box.expandByPoint(new THREE.Vector2(...toScene(plan, x, y)))
  }
  if (box.isEmpty()) box.set(new THREE.Vector2(-10, -10), new THREE.Vector2(10, 10))
  return box
}

/** Soft sky light plus one sun from the north-west that casts the only shadows (walls and furniture). */
function Lights({ plan, floors, palette, lift }: { plan: Plan; floors: number[]; palette: PlanPalette; lift: (index: number) => number }) {
  const sun = useRef<THREE.DirectionalLight>(null)
  const invalidate = useThree((state) => state.invalidate)
  const key = floors.join(',')
  useLayoutEffect(() => {
    const light = sun.current
    if (!light) return
    const box = floorBox(plan, floors)
    const centre = box.getCenter(new THREE.Vector2())
    const heights = floors.map(lift)
    const low = Math.min(...heights)
    const top = Math.max(...heights)
    const radius = box.getSize(new THREE.Vector2()).length() / 2 + 2 + (top - low)
    light.position.set(centre.x - 18, top + 40, centre.y - 24)
    light.target.position.set(centre.x, (top + low) / 2, centre.y)
    light.target.updateMatrixWorld()
    const camera = light.shadow.camera
    camera.left = -radius
    camera.right = radius
    camera.top = radius
    camera.bottom = -radius
    camera.near = 1
    camera.far = 160 + (top - low) * 2
    camera.updateProjectionMatrix()
    light.shadow.mapSize.set(2048, 2048)
    light.shadow.map?.dispose()
    light.shadow.map = null
    invalidate()
    // floors is compared through its key
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [plan, key, lift, invalidate])
  return (
    <>
      <hemisphereLight args={[palette.sky, palette.bounce, 2.4]} />
      <directionalLight ref={sun} intensity={0.9} castShadow shadow-bias={-0.0004} shadow-normalBias={0.02} shadow-radius={6} />
    </>
  )
}

const shadeMaterial = (strength: number) =>
  new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    uniforms: { strength: { value: strength } },
    vertexShader: `attribute float alpha; varying float vAlpha;
      void main() { vAlpha = alpha; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
    fragmentShader: `uniform float strength; varying float vAlpha;
      void main() { gl_FragColor = vec4(0.0, 0.0, 0.0, vAlpha * vAlpha * strength); }`,
  })

const FADED_OPACITY = 0.12 // floors below the current one: almost transparent, just enough to read their shape

function FloorModel({ geometry, palette, floor, furniture, faded = false }: {
  geometry: FloorGeometry
  palette: PlanPalette
  floor: number
  furniture: boolean
  faded?: boolean
}) {
  const invalidate = useThree((state) => state.invalidate)
  const shade = useMemo(() => shadeMaterial(palette.ao), [palette.ao])
  useEffect(() => () => shade.dispose(), [shade])
  useEffect(() => invalidate(), [geometry, faded, invalidate])
  // see-through for floors above: every material at FADED_OPACITY, no depth writes, no shadows, not pickable
  const fade = (opacity = 1) => (faded ? { transparent: true, opacity: opacity * FADED_OPACITY, depthWrite: false } : { transparent: opacity < 1, opacity })
  const solid = !faded

  return (
    <group key={faded ? 'faded' : 'solid'}>
      <mesh geometry={geometry.fills} receiveShadow={solid}>
        <meshLambertMaterial vertexColors side={THREE.DoubleSide} {...fade()} />
      </mesh>
      <mesh geometry={geometry.slab}>
        <meshLambertMaterial color={palette.slab} side={THREE.DoubleSide} {...fade()} />
      </mesh>
      {solid && <mesh geometry={geometry.shade} material={shade} renderOrder={1} />}
      {solid && furniture && <mesh geometry={geometry.contact} material={shade} renderOrder={1} />}
      <lineSegments geometry={geometry.lines} renderOrder={2}>
        <lineBasicMaterial color={palette.hairline} {...fade(0.8)} />
      </lineSegments>
      <mesh geometry={geometry.walls} castShadow={solid} receiveShadow={solid}>
        <meshLambertMaterial color={palette.clay} side={THREE.DoubleSide} polygonOffset polygonOffsetFactor={1} polygonOffsetUnits={1} {...fade()} />
      </mesh>
      <lineSegments geometry={geometry.wallEdges}>
        <lineBasicMaterial color={palette.edge} {...fade()} />
      </lineSegments>
      {solid && (
        <mesh geometry={geometry.doors} castShadow>
          <meshLambertMaterial color={palette.materials.oak} side={THREE.DoubleSide} />
        </mesh>
      )}
      {/* floors above show only their shell: furniture of two see-through floors on top of each other is noise */}
      {furniture && solid && (
        <>
          <mesh geometry={geometry.furniture} castShadow={solid} receiveShadow={solid} userData={solid ? { furnitureFloor: floor } : {}}>
            <meshLambertMaterial vertexColors side={THREE.DoubleSide} polygonOffset polygonOffsetFactor={1} polygonOffsetUnits={1} {...fade()} />
          </mesh>
          <lineSegments geometry={geometry.furnitureEdges}>
            <lineBasicMaterial color={palette.edge} {...fade(0.55)} />
          </lineSegments>
        </>
      )}
    </group>
  )
}

/** The selection: a room gets a tinted floor plus a 1 px outline, a piece of furniture turns accent blue. */
function Selection({ plan, selected, palette, floors, colours }: { plan: Plan; selected: Selected | null; palette: PlanPalette; floors: FloorGeometry[]; colours: PlanSettings['colours'] }) {
  const invalidate = useThree((state) => state.invalidate)
  const space = selected?.kind === 'space' ? plan.spaces.find((item) => item.id === selected.id) ?? null : null
  const asset = selected?.kind === 'asset' ? plan.assets.find((item) => item.id === selected.id) ?? null : null

  useEffect(() => {
    if (!space) return
    const geometry = floors[space.floor]
    paintSpace(geometry, space.id, palette.selected)
    invalidate()
    return () => {
      paintSpace(geometry, space.id, fillOf(palette, space, colours))
      invalidate()
    }
  }, [space, floors, palette, colours, invalidate])

  useEffect(() => {
    if (!asset) return
    const geometry = floors[asset.floor]
    paintAsset(geometry.furniture, geometry.furnitureIndex, asset.id, palette.selectedEdge)
    invalidate()
    return () => {
      paintAsset(geometry.furniture, geometry.furnitureIndex, asset.id, null)
      invalidate()
    }
  }, [asset, floors, palette, invalidate])

  const outline = useMemo(() => {
    if (!space) return null
    const points = space.polygon.map(([x, y]) => {
      const [X, Z] = toScene(plan, x, y)
      return new THREE.Vector3(X, 0.01, Z)
    })
    return new THREE.BufferGeometry().setFromPoints(points)
  }, [plan, space])
  useEffect(() => () => outline?.dispose(), [outline])

  if (!outline) return null
  return (
    <lineLoop geometry={outline} renderOrder={3}>
      <lineBasicMaterial color={palette.selectedEdge} />
    </lineLoop>
  )
}

/** Mouse-over tint: halfway between the room's own colour and the selection colour. */
function Hover({ plan, id, palette, floors, colours }: { plan: Plan; id: string; palette: PlanPalette; floors: FloorGeometry[]; colours: PlanSettings['colours'] }) {
  const invalidate = useThree((state) => state.invalidate)
  useEffect(() => {
    const space = plan.spaces.find((item) => item.id === id)
    if (!space) return
    const geometry = floors[space.floor]
    const own = fillOf(palette, space, colours)
    paintSpace(geometry, id, '#' + new THREE.Color(own).lerp(new THREE.Color(palette.selected), 0.5).getHexString())
    invalidate()
    return () => {
      paintSpace(geometry, id, own)
      invalidate()
    }
  }, [plan, id, palette, floors, colours, invalidate])
  return null
}

const offsetFor = (polar: number, azimuth: number) =>
  new THREE.Vector3().setFromSphericalCoords(CAMERA_DISTANCE, polar, azimuth)

/** Camera framing: the zoom that fits the shown floors (walls included, stacked heights included) into the free
 * part of the screen, and the target that centres them there. */
function frame(plan: Plan, floors: number[], lift: (index: number) => number, view: { polar: number; azimuth: number }, size: { width: number; height: number }, insets: Insets) {
  const box = floorBox(plan, floors)
  const probe = new THREE.OrthographicCamera()
  probe.position.copy(offsetFor(view.polar, view.azimuth))
  probe.up.set(0, 1, 0)
  probe.lookAt(0, 0, 0)
  probe.updateMatrixWorld()
  const inverse = probe.matrixWorldInverse
  // the outline's own corners, not its bounding box: an L-shaped plan seen at 45° wastes half its box
  const extent = new THREE.Box2()
  const p = new THREE.Vector3()
  for (const space of plan.spaces) {
    if (!floors.includes(space.floor)) continue
    for (const [x, y] of space.polygon) {
      const [X, Z] = toScene(plan, x, y)
      for (const height of [lift(space.floor), lift(space.floor) + WALL_CUT_M]) {
        p.set(X, height, Z).applyMatrix4(inverse)
        extent.expandByPoint(new THREE.Vector2(p.x, p.y))
      }
    }
  }
  const free = {
    width: Math.max(80, size.width - insets.left - insets.right - FIT_MARGIN_PX * 2),
    height: Math.max(80, size.height - insets.top - insets.bottom - FIT_MARGIN_PX * 2),
  }
  const span = extent.getSize(new THREE.Vector2())
  const zoom = Math.min(MAX_ZOOM, free.width / Math.max(span.x, 1), free.height / Math.max(span.y, 1))
  // centre of the drawing in camera space, back to world, then shifted so it sits in the middle of the free area
  const mid = extent.getCenter(new THREE.Vector2())
  const right = new THREE.Vector3().setFromMatrixColumn(probe.matrixWorld, 0)
  const up = new THREE.Vector3().setFromMatrixColumn(probe.matrixWorld, 1)
  const forward = new THREE.Vector3().setFromMatrixColumn(probe.matrixWorld, 2)
  const middle = box.getCenter(new THREE.Vector2())
  const centre = new THREE.Vector3(middle.x, 0, middle.y)
  const along = centre.clone().applyMatrix4(inverse)
  const target = centre
    .clone()
    .addScaledVector(right, mid.x - along.x)
    .addScaledVector(up, mid.y - along.y)
    .addScaledVector(right, -(insets.left - insets.right) / 2 / zoom)
    .addScaledVector(up, (insets.top - insets.bottom) / 2 / zoom)
  // keep the target on the ground plane: slide along the view direction
  if (Math.abs(forward.y) > 1e-6) target.addScaledVector(forward, -target.y / forward.y)
  return { target, zoom }
}

type Pose = { target: THREE.Vector3; zoom: number; polar: number; azimuth: number }
type Move = { t: number; from: Pose; to: Pose }

/** Frames the shown floors (tilted) whenever they or fitKey change, easing there. Tilting is free in between
 * (0 = straight down … MAX_POLAR); a nearly flat tilt snaps flat when the gesture ends, and the current look
 * (flat or tilted) is reported so a flat view can stop spreading the floors. */
function Rig({ plan, floor, floors, stacked, insets, fitKey, onTilt }: {
  plan: Plan
  floor: number
  floors: number[]
  stacked: boolean
  insets: Insets
  fitKey: number
  onTilt: (mode: ViewMode) => void
}) {
  const camera = useThree((state) => state.camera) as THREE.OrthographicCamera
  const size = useThree((state) => state.size)
  const invalidate = useThree((state) => state.invalidate)
  const controls = useThree((state) => state.controls) as MapControlsImpl | null
  // Insets are read when a fit happens, not watched: the sheet moving must not move the map.
  const insetsRef = useRef(insets)
  insetsRef.current = insets
  const onTiltRef = useRef(onTilt)
  onTiltRef.current = onTilt
  const stackedRef = useRef(stacked)
  stackedRef.current = stacked
  const move = useRef<Move | null>(null)
  const first = useRef(true)
  const reported = useRef<ViewMode | null>(null)
  const key = floors.join(',')

  const report = (polar: number) => {
    const mode: ViewMode = polar < FLAT_BELOW ? '2d' : '3d'
    if (mode !== reported.current) {
      reported.current = mode
      onTiltRef.current(mode)
    }
  }

  const place = (pose: Pose) => {
    if (!controls) return
    controls.target.copy(pose.target)
    camera.position.copy(pose.target).add(offsetFor(pose.polar, pose.azimuth))
    camera.up.set(0, 1, 0)
    camera.lookAt(pose.target)
    camera.zoom = pose.zoom
    camera.updateProjectionMatrix()
  }

  useEffect(() => {
    if (!controls) return
    const pose = (): Pose => ({ target: controls.target.clone(), zoom: camera.zoom, polar: controls.getPolarAngle(), azimuth: controls.getAzimuthalAngle() })
    // Report only when a gesture ends: a React update in the middle of a drag would re-render the controls and
    // drop the pointer (the drag then never ends and the controls stop responding).
    const onEnd = () => {
      const polar = controls.getPolarAngle()
      if (polar > FLAT_POLAR * 2 && polar < FLAT_BELOW) {
        move.current = { t: 0, from: pose(), to: { ...pose(), polar: FLAT_POLAR } }
        invalidate()
      } else report(polar)
    }
    controls.addEventListener('end', onEnd)
    return () => controls.removeEventListener('end', onEnd)
    // report reads refs only
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [controls, camera, invalidate, plan])

  useEffect(() => {
    if (!controls) return
    // keep the user's own turn
    const azimuth = first.current ? TILTED.azimuth : controls.getAzimuthalAngle()
    const polar = TILTED.polar
    // the whole fixed-gap stack, or the floor you are on: the camera focuses on your floor; the others stay spread
    // above and below it, out of frame until you zoom out
    const framed = stacked ? floors : [floor]
    const lift = (i: number) => (stacked ? floorLift(i) : 0)
    const fit = frame(plan, framed, lift, { polar, azimuth }, size, insetsRef.current)
    const to = { target: fit.target, zoom: fit.zoom, polar, azimuth }
    if (first.current) {
      first.current = false
      place(to)
      controls.update()
      report(to.polar)
      invalidate()
      return
    }
    const from = { target: controls.target.clone(), zoom: camera.zoom, polar: controls.getPolarAngle(), azimuth: controls.getAzimuthalAngle() }
    move.current = { t: 0, from, to }
    invalidate()
    // place reads refs only; floors is compared through its key
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [plan, key, floor, stacked, fitKey, controls, size.width, size.height, camera, invalidate])

  useFrame((_, delta) => {
    const current = move.current
    if (!current || !controls) return
    // on-demand rendering: the first frame's delta is the whole idle time before it, so cap the step
    current.t = Math.min(1, current.t + Math.min(delta, 1 / 30) / MOVE_SECONDS)
    const k = 1 - Math.pow(1 - current.t, 3)
    const { from, to } = current
    const turn = Math.atan2(Math.sin(to.azimuth - from.azimuth), Math.cos(to.azimuth - from.azimuth)) // the short way round
    place({
      target: from.target.clone().lerp(to.target, k),
      zoom: from.zoom + (to.zoom - from.zoom) * k,
      polar: from.polar + (to.polar - from.polar) * k,
      azimuth: from.azimuth + turn * k,
    })
    if (current.t >= 1) {
      move.current = null
      controls.update()
      report(to.polar)
    }
    invalidate()
  })

  const onStart = useCallback(() => {
    move.current = null
  }, [])

  return (
    <MapControls
      makeDefault
      enableDamping={false}
      screenSpacePanning
      minZoom={1}
      maxZoom={MAX_ZOOM}
      minPolarAngle={FLAT_POLAR}
      maxPolarAngle={MAX_POLAR}
      zoomToCursor
      onStart={onStart}
    />
  )
}

/** Screen point → what is under it: a piece of furniture first, else the smallest space on that floor (rooms win
 * over the hall around them). With floors stacked, the floor nearest the camera wins. */
function Picker({ plan, floors, lift, stacked, geometries, pick }: {
  plan: Plan
  floors: number[]
  lift: (index: number) => number
  stacked: boolean
  geometries: FloorGeometry[]
  pick: React.RefObject<(x: number, y: number) => Hit | null>
}) {
  const { camera, size, scene } = useThree()
  useEffect(() => {
    const raycaster = new THREE.Raycaster()
    pick.current = (x: number, y: number) => {
      raycaster.setFromCamera(new THREE.Vector2((x / size.width) * 2 - 1, -(y / size.height) * 2 + 1), camera)
      if (!stacked) {
        const furniture: THREE.Object3D[] = []
        scene.traverse((object) => object.userData.furnitureFloor !== undefined && furniture.push(object))
        const [first] = raycaster.intersectObjects(furniture, false)
        if (first?.face) {
          const index = first.object.userData.furnitureFloor as number
          const id = assetAt(geometries[index].furnitureIndex, first.face.a)
          if (id) return { floor: index, selected: { kind: 'asset', id } }
        }
      }
      const hits = floors
        .map((floor) => {
          const plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), -lift(floor))
          const point = raycaster.ray.intersectPlane(plane, new THREE.Vector3())
          return point ? { floor, point, distance: point.distanceTo(raycaster.ray.origin) } : null
        })
        .filter((hit): hit is { floor: number; point: THREE.Vector3; distance: number } => hit !== null)
        .sort((a, b) => a.distance - b.distance)
      for (const hit of hits) {
        const [px, py] = fromScene(plan, hit.point.x, hit.point.z)
        let best: PlanSpace | null = null
        for (const space of plan.spaces) {
          if (space.floor !== hit.floor || !contains(space.polygon, px, py)) continue
          if (!best || space.area_m2 < best.area_m2) best = space
        }
        if (best) return { floor: hit.floor, selected: { kind: 'space', id: best.id } }
      }
      return null
    }
  }, [plan, floors, lift, stacked, geometries, camera, size, scene, pick])
  return null
}

const FONT = '-apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'
const NAME_PX = 12
const REF_PX = 11
const LABEL_GAP_PX = 3

/** Free width and height (metres) through the label point: the span of the horizontal and vertical lines through
 * it that stays inside the polygon. Labels must fit these, not just a circle. */
function spans(polygon: [number, number][], [x, y]: [number, number]): [number, number] {
  const span = (axis: 0 | 1) => {
    const along = axis === 0 ? x : y
    const fixed = axis === 0 ? y : x
    const cuts: number[] = []
    for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
      const a = polygon[j]
      const b = polygon[i]
      const fa = a[1 - axis]
      const fb = b[1 - axis]
      if (fa > fixed !== fb > fixed) cuts.push(a[axis] + ((fixed - fa) / (fb - fa)) * (b[axis] - a[axis]))
    }
    cuts.sort((p, q) => p - q)
    for (let k = 0; k + 1 < cuts.length; k += 2) if (cuts[k] <= along && along <= cuts[k + 1]) return cuts[k + 1] - cuts[k]
    return 0
  }
  return [span(0), span(1)]
}

/** Splits "Quality lab 0.21" into the words and the ref, so the ref can sit on its own quieter line. */
function labelParts(space: PlanSpace): [string, string] {
  const name = space.name.trim()
  if (space.ref && name.endsWith(space.ref) && name.length > space.ref.length) {
    return [name.slice(0, -space.ref.length).trim(), space.ref]
  }
  return [name, '']
}

function LabelPainter({ plan, floor, stacked, tags: showTags, lift, palette, canvas, selected, skip }: {
  skip: Set<string>
  tags: boolean
  lift: (index: number) => number
  plan: Plan
  floor: number
  stacked: boolean
  palette: PlanPalette
  canvas: React.RefObject<HTMLCanvasElement | null>
  selected: Selected | null
}) {
  const { camera, size, viewport } = useThree()
  const selectedSpace = selected?.kind === 'space' ? selected.id : null
  const order = useMemo(
    () =>
      plan.spaces
        .filter((space) => space.floor === floor && space.type !== 'corridor' && (!skip.has(space.id) || space.id === selectedSpace))
        .sort((a, b) => (b.id === selectedSpace ? 1 : 0) - (a.id === selectedSpace ? 1 : 0) || b.area_m2 - a.area_m2)
        .map((space) => ({ space, free: spans(space.polygon, space.label) })),
    [plan, floor, selectedSpace, skip],
  )
  // Floor name tags for the stacked view, at each floor's west corner.
  const tags = useMemo(
    () =>
      plan.floors.map((item, index) => {
        const box = floorBox(plan, [index])
        return { name: item.name, index, at: new THREE.Vector3(box.min.x, lift(index) + WALL_CUT_M, box.max.y) }
      }),
    [plan, lift],
  )
  const invalidate = useThree((state) => state.invalidate)
  useEffect(() => invalidate(), [order, palette, stacked, tags, invalidate])

  useFrame(() => {
    const element = canvas.current
    if (!element) return
    const dpr = viewport.dpr
    if (element.width !== Math.round(size.width * dpr) || element.height !== Math.round(size.height * dpr)) {
      element.width = Math.round(size.width * dpr)
      element.height = Math.round(size.height * dpr)
    }
    const context = element.getContext('2d')
    if (!context) return
    context.setTransform(dpr, 0, 0, dpr, 0, 0)
    context.clearRect(0, 0, size.width, size.height)
    context.textBaseline = 'middle'
    context.lineJoin = 'round'
    camera.updateMatrixWorld()
    const toScreen = (point: THREE.Vector3) => {
      const p = point.clone().project(camera)
      return [((p.x + 1) / 2) * size.width, ((1 - p.y) / 2) * size.height] as const
    }

    if (showTags) {
      context.textAlign = 'right'
      for (const tag of tags) {
        const [sx, sy] = toScreen(tag.at)
        context.font = `700 13px ${FONT}`
        // a pill right-aligned just left of the floor, never pushed off the left edge of the screen
        const width = context.measureText(tag.name).width
        const x = Math.max(width + 22, sx - 10)
        context.fillStyle = palette.halo
        context.beginPath()
        context.roundRect(x - width - 10, sy - 12, width + 20, 24, 12)
        context.fill()
        context.fillStyle = tag.index === floor ? palette.selectedEdge : palette.label
        context.fillText(tag.name, x, sy)
      }
      if (stacked) return
    }

    context.textAlign = 'center'
    // A tilted room looks shallower than it is (foreshortened by the cosine of the tilt) and turned, so unless the
    // view is flat and north-up the label must fit the room's smaller side.
    const pixelsPerMetre = (camera as THREE.OrthographicCamera).zoom
    const tilt = Math.max(0.3, -camera.getWorldDirection(new THREE.Vector3()).y)
    const screenUp = new THREE.Vector3(0, 1, 0).applyQuaternion(camera.quaternion)
    const flat = tilt > 0.99 && screenUp.z < -0.99
    const taken: [number, number, number, number][] = []
    const point = new THREE.Vector3()

    for (const { space, free } of order) {
      const [X, Z] = toScene(plan, space.label[0], space.label[1])
      const [sx, sy] = toScreen(point.set(X, 0.02, Z))
      if (sx < -80 || sy < -40 || sx > size.width + 80 || sy > size.height + 40) continue
      const across = flat ? free[0] : Math.min(free[0], free[1])
      const freeWidth = across * pixelsPerMetre - 8
      const freeHeight = (flat ? free[1] : Math.min(free[0], free[1])) * pixelsPerMetre * tilt - 6
      const [name, ref] = labelParts(space)
      context.font = `600 ${NAME_PX}px ${FONT}`
      const nameWidth = context.measureText(name).width
      const isSelected = space.id === selectedSpace
      if (!isSelected && (nameWidth > freeWidth || freeHeight < NAME_PX + 2)) continue
      const showRef = Boolean(ref) && freeHeight > NAME_PX + REF_PX + LABEL_GAP_PX + 8
      const height = showRef ? NAME_PX + REF_PX + LABEL_GAP_PX : NAME_PX
      const box: [number, number, number, number] = [sx - nameWidth / 2 - 4, sy - height / 2 - 3, sx + nameWidth / 2 + 4, sy + height / 2 + 3]
      if (!isSelected && taken.some((other) => box[0] < other[2] && box[2] > other[0] && box[1] < other[3] && box[3] > other[1])) continue
      taken.push(box)
      const nameY = showRef ? sy - (REF_PX + LABEL_GAP_PX) / 2 : sy
      context.lineWidth = 3
      context.strokeStyle = palette.halo
      context.fillStyle = isSelected ? palette.selectedEdge : palette.label
      context.strokeText(name, sx, nameY)
      context.fillText(name, sx, nameY)
      if (showRef) {
        context.font = `500 ${REF_PX}px ${FONT}`
        const refY = sy + (NAME_PX + LABEL_GAP_PX) / 2
        context.fillStyle = palette.labelSoft
        context.strokeText(ref, sx, refY)
        context.fillText(ref, sx, refY)
      }
    }
  })
  return null
}
