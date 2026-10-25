// The plan canvas: the building as a matte clay cutaway model. One floor at a time, or every floor stacked at its
// real height so you can see how they sit on each other (tap one to step into it). The camera tilts freely
// between isometric and straight-down (a flat plan) like a map: right-drag, Ctrl/Shift + drag or a two-finger
// drag tilts and turns, one finger or the mouse pans, pinch or wheel zooms.
// Tap a room or a piece of furniture to select it. Renders on demand only: a frame is drawn when the camera or
// the drawing changes, never in idle. Labels (rooms, or floor names when stacked) are painted on a 2D canvas over
// the WebGL one after every frame.
// The model rises out of the ground when it first appears (Reveal). Over the landing map (src/map/bridge.ts) the
// camera starts from the map's own camera and eases to the first framing, and every frame hands the camera to the
// map so the city stays in register under the model.
// `focus` frames what an answer is about (its rooms, items or route part) instead of the whole floor. The "you are
// here" figure is dragged out of its dock (bottom right) onto the plan, or the dock is tapped and then the plan;
// dragged again to move it. Put down off the building it stands at the nearest entrance.

import { MapControls } from '@react-three/drei'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { Footprints } from 'lucide-react'
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import type { MapControls as MapControlsImpl } from 'three-stdlib'
import type { FleetObject, Plan, PlanOpening, PlanSpace } from '../api'
import { MAX_MAP_PITCH, type ShellBlock, type View } from '../map/bridge'
import { assetAt, paintAsset } from './furniture'
import { buildFloor, buildFloors, contains, fillOf, fromScene, paintSpace, toScene, WALL_CUT_M, type FloorGeometry } from './geometry'
import type { PlanPalette } from './palette'
import { ObjectMarkers, ObjectsLayer } from './ObjectsLayer'
import { Pins, PinTracker, pinsFor, type Pin } from './pins'
import type { PlanSettings } from './settings'
import { askForCompass, compassLikely, shortest, turnFor, watchCompass } from './compass'
import { StreetView, type Street } from './StreetView'
import { DashedWalk, PersonGlyph, StoryLayer, StoryMarkers, storyMarkers } from '../dev/StoryLayer'
import type { Story } from '../dev/story'

export type Insets = { top: number; right: number; bottom: number; left: number }
export type ViewMode = '3d' | '2d'
export type Selected = { kind: 'space' | 'asset'; id: string }
/** Points to frame ([x, y, floor index], plan metres), at least `span` metres across; a new `key` moves the camera.
 * On a single floor only that floor's points count; none there = the whole floor. */
/** `heading`: a direction in the plan frame (unit) the camera turns to face, e.g. the way a route step goes */
export type Focus = { key: number; points: [number, number, number][]; span?: number; heading?: [number, number] }
/** The "you are here" figure: where it stands, and the room (its label); outside the building, `door` is the
 * nearest entrance (the room behind it is `space`, and routes start there) */
export type Me = { at: [number, number]; floor: number; space: string; label: string; door?: [number, number] }
type Hit = { floor: number; selected: Selected | null }

type Props = {
  plan: Plan
  floor: number
  stacked: boolean
  /** stacked: only these floors (a route's overview), at their real elevations; else every floor */
  only?: number[]
  palette: PlanPalette
  selected: Selected | null
  insets: Insets
  /** the free part of the screen the whole building is centred in (default `insets`); answers keep `insets` */
  frameInsets?: Insets
  /** the free part of the screen an answer's rooms or route are framed in (default `insets`) */
  focusInsets?: Insets
  fitKey: number
  onSelect: (selected: Selected | null) => void
  onPickFloor: (floor: number) => void
  onTilt: (mode: ViewMode) => void
  /** in 3D, show every floor spread apart around the current one so none hides another */
  spread: boolean
  settings: PlanSettings
  /** dev tool: the current answer drawn over the plan (src/dev/StoryLayer.tsx) */
  story: Story
  /** draw the model's own ground grid (off when the map is the ground) */
  ground?: boolean
  /** shown in its city: the map's own blocks of this building (drawn as a wireframe) and the map's ground colour
   * (floors under the ground are seen through it) */
  city?: { shell: ShellBlock[]; ground: string }
  /** the map under the model: its camera now (where the model's camera starts), and the model's camera on every frame */
  camera?: { intro: () => View | null; follow?: (view: View) => void }
  /** a tap that hit nothing of the building; true when it was used (a pin on the map around it) */
  onMiss?: (x: number, y: number) => boolean
  /** access mode: moving objects to draw (src/plan/ObjectsLayer.tsx) */
  objects?: FleetObject[]
  focus?: Focus | null
  /** the "you are here" figure, and where the user put it (null = taken off the plan); no onMe = no figure */
  me?: Me | null
  onMe?: (me: Me | null) => void
  /** the badge at the end of a walk to a nearby building */
  onNext?: () => void
  /** an SVG group over the canvas drawn in building metres (src/edit/EditLayer.tsx): kept in register with the
   * current floor's plane on every frame (the camera is orthographic, so the plane maps to the screen affinely) */
  align?: React.RefObject<SVGGElement | null>
  /** every tap on the building (or, on one floor, beside it): the floor, the point in plan metres and the pixels per
   * metre there. Returning true takes the tap (no selecting); a tap on another floor still steps onto it. */
  onTap?: (tap: Tap) => boolean
}

export type Tap = { floor: number; at: [number, number]; pixelsPerMetre: number }

const FIT_MARGIN_PX = 24
const MOVE_SECONDS = 0.55
const INTRO_SECONDS = 1.1 // from the map's camera to the first framing
const REVEAL_SECONDS = 0.9 // the model rising out of the ground
const TAP_SLOP_PX = 8
const WALL_SNAP_M = 0.6 // put down on a wall: the room this close counts
const MAX_ZOOM = 220
const CAMERA_DISTANCE = 400
const FLAT_POLAR = 0.0001
const MAX_POLAR = 1.2
const MAX_POLAR_ON_MAP = THREE.MathUtils.degToRad(MAX_MAP_PITCH) // over the map: beyond it the map drops its tiles
const FLAT_BELOW = 0.14 // a tilt this small snaps to straight-down when the gesture ends
const SLIDE_SECONDS = 0.5
const GROUND_BELOW_M = 0.36 // just under the slab edge
const TILTED = { polar: 0.98, azimuth: Math.PI / 4 } // ~34° above the horizon, looking from the south-east corner

const HEADING_RATE = 6 // how fast heading-up turns the map toward the phone (per second; readings are noisy)
const COMPASS_WAIT_MS = 2000 // no reading by then: this device has no compass
const STOREY_M = 3 // a floor without its own height (height_m) in street view

// "All floors" stacks every floor at its real elevation (from the lowest floor), so the building keeps its proportions
const floorLift = (plan: Plan, index: number) => (plan.floors[index]?.elevation_m ?? 0) - (plan.floors[0]?.elevation_m ?? 0)
export function PlanView(props: Props) {
  const { plan, floor, stacked, only, palette, selected, insets, frameInsets, focusInsets, fitKey, onSelect, onPickFloor, onTilt, spread, settings, story, ground = true, city, camera, onMiss, objects, focus = null, me = null, onMe, onNext, align, onTap } = props
  const groundRef = useRef<THREE.Mesh>(null)
  const labels = useRef<HTMLCanvasElement>(null)
  const { wallHeight, colours } = settings
  const floors = useMemo(() => buildFloors(plan, palette, { wallHeight, colours }), [plan, palette, wallHeight, colours])
  const [hovered, setHovered] = useState<string | null>(null)
  // all floors stacked: the floor under the mouse lights up (a tap steps into it)
  const [hoveredFloor, setHoveredFloor] = useState<number | null>(null)
  useEffect(() => setHoveredFloor(null), [stacked])
  const pinList = useMemo(() => (settings.pins && !stacked ? pinsFor(plan, floor) : []), [settings.pins, stacked, plan, floor])
  const pinElements = useRef(new Map<string, HTMLElement>())
  const pinnedSpaces = useMemo(() => new Set(pinList.map((pin) => pin.space).filter((id): id is string => Boolean(id))), [pinList])
  // Single-floor 3D view: the current floor (at y = 0) plus the floors below it at their real height, nearly
  // transparent, for context; floors above are not drawn at all. "All floors" stacks them at their real elevations.
  const spreading = spread && !stacked
  const mode = stacked ? 'stacked' : 'floor'
  const elevation = useCallback((index: number) => plan.floors[index]?.elevation_m ?? 0, [plan])
  const stackLift = useCallback((index: number) => floorLift(plan, index), [plan])
  const lift = useCallback(
    (index: number) => (stacked ? stackLift(index) : spreading ? elevation(index) - elevation(floor) : 0),
    [stacked, spreading, floor, elevation, stackLift],
  )
  useEffect(() => () => floors.forEach(disposeFloor), [floors])
  const down = useRef<{ x: number; y: number } | null>(null)
  const pick = useRef<(x: number, y: number) => Hit | null>(() => null)
  // screen point → plan metres on a floor's plane (for the figure's drop)
  const unproject = useRef<(x: number, y: number, floor: number) => [number, number] | null>(() => null)
  const zoom = useRef<() => number>(() => 1) // pixels per metre (the orthographic camera's zoom)
  // the ground (the map's, over the map) under the ground floor; one floor alone stands on it
  const groundY = (spreading || stacked ? lift(groundIndex(plan)) : 0) - GROUND_BELOW_M
  const shown = stacked ? only?.filter((index) => floors[index]) ?? [...floors.keys()] : spreading ? [...floors.keys()].filter((i) => i <= floor) : [floor]
  const markers = useMemo(() => {
    const list = storyMarkers(plan, story)
    if (me && onMe) list.push({ key: 'me', kind: 'me', floor: me.floor, at: me.at, label: me.label })
    if (me && onMe && me.door) list.push({ key: 'me-door', kind: 'place', floor: me.floor, at: me.door, label: 'Entrance' })
    return list
  }, [plan, story, me, onMe])
  /** Where the figure would stand if put down at (x, y) in the plan's box: on the floor under it (stacked: the
   * ground floor off the building), in the smallest room there; off the building it stays where it was put and
   * takes the nearest entrance of that floor (else of any floor), so it is clear which door you are at. */
  const resolveMe = (x: number, y: number): Me | null => {
    const target = stacked ? pick.current(x, y)?.floor ?? groundIndex(plan) : floor
    const at = unproject.current(x, y, target)
    if (!at) return null
    let best: PlanSpace | null = null
    let near: { space: PlanSpace; at: [number, number]; away: number } | null = null
    for (const space of plan.spaces) {
      if (space.floor !== target) continue
      if (contains(space.polygon, at[0], at[1])) {
        if (!best || space.area_m2 < best.area_m2) best = space
      } else if (!best) {
        const edge = nearestEdge(space.polygon, at)
        if (edge.away < WALL_SNAP_M && (!near || edge.away < near.away)) near = { space, ...edge }
      }
    }
    if (best) return { at, floor: target, space: best.id, label: best.name }
    if (near) return { at: near.at, floor: target, space: near.space.id, label: near.space.name } // on a wall
    const entrances = plan.openings.filter((opening) => opening.entrance || opening.kind === 'entrance')
    const here = entrances.filter((opening) => opening.floor === target)
    let door: PlanOpening | null = null
    let doorM = Infinity
    for (const opening of here.length ? here : entrances) {
      const away = Math.hypot(opening.position[0] - at[0], opening.position[1] - at[1])
      if (away < doorM) [door, doorM] = [opening, away]
    }
    const inside = door && plan.spaces.find((space) => space.id === (door.space ?? door.spaces[0]))
    if (!door || !inside) return null
    return { at, floor: door.floor, space: inside.id, label: `Near entrance · ${inside.name}`, door: door.position }
  }
  /** Put the figure where it was dropped (x, y in the plan's box); nowhere to stand, it goes back where it was. */
  const dropMe = (x: number, y: number) => {
    if (!onMe) return
    const next = resolveMe(x, y)
    onMe(next ?? (me ? { ...me } : null)) // a fresh object: the tracker puts it back
  }
  const dock = useRef<HTMLButtonElement>(null)
  const dockDrag = useRef<{ x: number; y: number; moved: boolean } | null>(null)
  // the figure in the hand (dragged out of the dock, or following the mouse after a tap on the dock), with where it
  // would land
  const ghost = useRef<HTMLDivElement>(null)
  const showGhost = (x: number, y: number) => {
    const node = ghost.current
    if (!node) return
    node.style.display = 'block'
    node.style.transform = `translate(${x}px, ${y}px)`
    const name = node.querySelector('span span')
    if (name) name.textContent = resolveMe(x, y)?.label ?? 'Not here'
  }
  const hideGhost = () => void (ghost.current && (ghost.current.style.display = 'none'))
  // a tap on the dock: the next tap on the plan puts the figure there (Esc or the dock again cancels)
  const [placing, setPlacing] = useState(false)
  useEffect(() => {
    if (!placing) return hideGhost()
    const onKey = (event: KeyboardEvent) => event.key === 'Escape' && setPlacing(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [placing])
  useEffect(() => {
    if (!onMe) setPlacing(false)
  }, [onMe])
  const markerElements = useRef(new Map<string, HTMLElement>())
  const objectElements = useRef(new Map<string, HTMLElement>())
  const rose = useRef<HTMLSpanElement>(null)
  const northUp = useRef<(() => void) | null>(null)
  // street view: down to eye level where the figure stands, or (no figure) where the next tap on the plan is
  const azimuth = useRef(TILTED.azimuth) // the plan camera's turn, kept by CompassTracker: street view faces the same way
  const [street, setStreet] = useState<Street | null>(null)
  // heading-up (phones): the map turns so the way you face is up; a tap on the compass when north is already up
  const [headingUp, setHeadingUp] = useState(false)
  const canHeadingUp = useMemo(compassLikely, [])
  const [streetArmed, setStreetArmed] = useState(false)
  useEffect(() => {
    setStreet(null)
    setStreetArmed(false)
  }, [plan.building.id])
  useEffect(() => {
    if (!streetArmed) return
    const onKey = (event: KeyboardEvent) => event.key === 'Escape' && setStreetArmed(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [streetArmed])
  const enterStreet = (at: [number, number], on: number) => setStreet({ at, floor: on, yaw: streetYaw(story.route?.line, at, on) ?? azimuth.current })
  // the floor at eye level: its walls at its full storey height (the plan cuts them low)
  const streetFloor = useMemo(
    () => (street ? buildFloor(plan, street.floor, palette, { wallHeight: plan.floors[street.floor]?.height_m || STOREY_M, colours }) : null),
    [plan, street?.floor, palette, colours], // eslint-disable-line react-hooks/exhaustive-deps
  )
  useEffect(() => () => void (streetFloor && disposeFloor(streetFloor)), [streetFloor])

  return (
    <div
      className={`plan${placing ? ' placing' : ''}${street ? ' in-street' : ''}`}
      onContextMenu={(event) => event.preventDefault()}
      onPointerDown={(event) => (down.current = { x: event.clientX, y: event.clientY })}
      onPointerMove={(event) => {
        if (placing && event.buttons) hideGhost() // panning while placing: the figure waits for the next hover
        if (event.pointerType !== 'mouse' || event.buttons) return
        if (placing) {
          const rect = event.currentTarget.getBoundingClientRect()
          showGhost(event.clientX - rect.left, event.clientY - rect.top)
          return
        }
        if (!stacked && !settings.hover) return
        const rect = event.currentTarget.getBoundingClientRect()
        const hit = pick.current(event.clientX - rect.left, event.clientY - rect.top)
        if (stacked) {
          const at = hit?.floor ?? null
          if (at !== hoveredFloor) setHoveredFloor(at)
          return
        }
        const id = hit?.selected?.kind === 'space' ? hit.selected.id : null
        if (id !== hovered) setHovered(id)
      }}
      onPointerLeave={() => {
        if (placing) hideGhost()
        setHovered(null)
        setHoveredFloor(null)
      }}
      style={(settings.hover && hovered) || (stacked && hoveredFloor !== null) ? { cursor: 'pointer' } : undefined}
      onPointerUp={(event) => {
        const start = down.current
        down.current = null
        if (!start || event.button !== 0 || Math.hypot(event.clientX - start.x, event.clientY - start.y) > TAP_SLOP_PX) return
        const rect = event.currentTarget.getBoundingClientRect()
        const [x, y] = [event.clientX - rect.left, event.clientY - rect.top]
        if (placing) {
          setPlacing(false)
          dropMe(x, y)
          return
        }
        if (streetArmed) {
          setStreetArmed(false)
          const spot = resolveMe(x, y)
          if (spot) enterStreet(spot.door ?? spot.at, spot.floor)
          return
        }
        const hit = pick.current(x, y)
        const tapped = hit?.floor ?? (stacked ? null : floor)
        const at = tapped === null ? null : unproject.current(x, y, tapped)
        if (onTap && tapped !== null && at && onTap({ floor: tapped, at, pixelsPerMetre: zoom.current() })) {
          if (stacked || tapped !== floor) onPickFloor(tapped)
          return
        }
        if (!hit && onMiss?.(event.clientX, event.clientY)) return
        // a tap on another floor (or on a floor of the stack) steps onto it and selects what is there, in one tap
        if (hit && (stacked || hit.floor !== floor)) {
          onPickFloor(hit.floor)
          if (hit.selected) onSelect(hit.selected)
        } else onSelect(hit?.selected ?? null)
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
        <Reveal>
        <Slide floor={floor} mode={mode} lift={lift} heightOf={spreading ? elevation : stackLift}>
          <Ground plan={plan} palette={palette} y={groundY} visible={ground} mesh={groundRef} />
          {city && (
            <City
              plan={plan}
              palette={palette}
              y={groundY}
              shell={city.shell}
            />
          )}
          {shown.map((index) => (
            <group key={index} position={[0, lift(index), 0]}>
              <FloorModel
                geometry={floors[index]}
                palette={palette}
                floor={index}
                furniture={settings.furniture === 'full'}
                faded={spreading && index < floor}
                under={index !== floor && (plan.floors[index]?.level ?? 0) < 0}
              />
            </group>
          ))}
          {mode === 'stacked' && shown.map((index) => (
            <group key={`tag-${index}`} position={[0, lift(index), 0]}>
              <FloorTag plan={plan} floor={index} name={plan.floors[index]?.name ?? ''} height={wallHeight} palette={palette} current={index === floor || index === hoveredFloor} />
            </group>
          ))}
          {mode === 'stacked' && hoveredFloor !== null && floors[hoveredFloor] && (
            <group position={[0, lift(hoveredFloor), 0]}>
              <FloorGlow geometry={floors[hoveredFloor]} palette={palette} />
            </group>
          )}
          {mode === 'floor' && <Selection plan={plan} selected={selected} palette={palette} floors={floors} colours={colours} />}
          {mode === 'floor' && settings.hover && hovered && hovered !== selected?.id && (
            <Hover plan={plan} id={hovered} palette={palette} floors={floors} colours={colours} />
          )}
          {me && onMe && me.door && shown.includes(me.floor) && (
            <DashedWalk plan={plan} from={me.at} to={me.door} floor={me.floor} colour={palette.selectedEdge} lift={lift} />
          )}
          <StoryLayer plan={plan} story={story} palette={palette} shown={shown} floor={floor} stacked={stacked} lift={lift} markers={markers} markerElements={markerElements} />
          {objects && objects.length > 0 && (
            <ObjectsLayer plan={plan} objects={objects} palette={palette} shown={shown} floor={floor} stacked={stacked} lift={lift} elements={objectElements} />
          )}
        </Slide>
        </Reveal>
        <Rig plan={plan} floor={floor} floors={shown} stacked={stacked} frameInsets={frameInsets ?? insets} focusInsets={focusInsets ?? insets} fitKey={fitKey} focus={focus} onTilt={onTilt} intro={camera?.intro} ground={groundRef} maxPolar={camera ? MAX_POLAR_ON_MAP : MAX_POLAR} northUp={northUp} headingUp={headingUp && !street} onNoCompass={() => setHeadingUp(false)} />
        <CompassTracker rose={rose} azimuth={azimuth} />
        {align && <Align plan={plan} y={stacked ? stackLift(floor) : lift(floor)} target={align} />}
        <Follow plan={plan} ground={groundRef} follow={camera?.follow} />
        <Picker plan={plan} floors={stacked ? shown : shown.filter((i) => i <= floor)} lift={lift} stacked={stacked} geometries={floors} pick={pick} unproject={unproject} zoom={zoom} />
        <LabelPainter plan={plan} floor={floor} stacked={stacked} rooms={mode === 'floor'} palette={palette} canvas={labels} selected={selected} skip={pinnedSpaces} />
        <PinTracker plan={plan} pins={pinList} elements={pinElements} />
      </Canvas>
      <canvas ref={labels} className="plan-labels" aria-hidden="true" />
      <button
        type="button"
        className={`plan-compass${headingUp ? ' heading-up' : ''}`}
        style={{ right: insets.right + 16, bottom: insets.bottom + 16 + (onMe ? 44 + 10 : 0) }}
        aria-label={headingUp ? 'Compass: following the phone, tap for north-up' : canHeadingUp ? 'Compass: turn the view north-up; tap again to follow the phone' : 'Compass: turn the view north-up'}
        title={headingUp ? 'Heading up · tap for north-up' : canHeadingUp ? 'North · tap for north-up, again to follow the phone' : 'North · tap to turn north-up'}
        onPointerDown={(event) => event.stopPropagation()}
        onPointerUp={(event) => event.stopPropagation()}
        aria-pressed={canHeadingUp ? headingUp : undefined}
        onClick={async () => {
          if (headingUp) {
            setHeadingUp(false)
            return northUp.current?.()
          }
          const northIsUp = Math.abs(shortest(azimuth.current, 0)) < 0.02
          if (canHeadingUp && northIsUp && (await askForCompass())) setHeadingUp(true)
          else northUp.current?.()
        }}
      >
        <span ref={rose} className="plan-compass-rose" aria-hidden="true">
          <svg viewBox="-23 -23 46 46">
            {COMPASS_TICKS.map((deg) => (
              <line key={deg} className={deg % 90 === 0 ? 'major' : undefined} x1="0" y1="-20" x2="0" y2={deg % 90 === 0 ? -16 : -18} transform={`rotate(${deg})`} />
            ))}
            <path className="needle-n" d="M0 -10.5 L2.4 0 L-2.4 0 Z" />
            <path className="needle-s" d="M0 10.5 L2.4 0 L-2.4 0 Z" />
            <circle className="hub" r="1.6" />
          </svg>
          <b>N</b>
        </span>
      </button>
      <Pins pins={pinList} elements={pinElements} onPick={(pin: Pin) => pin.space && onSelect({ kind: 'space', id: pin.space })} />
      <StoryMarkers markers={markers} elements={markerElements} onGoto={onPickFloor} onNext={onNext} onMeDrop={dropMe} onMePreview={(x, y) => resolveMe(x, y)?.label ?? null} />
      {onMe && (
        <div ref={ghost} className="me-ghost" aria-hidden="true">
          <span className="me-figure">
            <PersonGlyph />
            <span />
          </span>
        </div>
      )}
      {onMe && (
        <button
          type="button"
          className={`plan-street${streetArmed ? ' armed' : ''}`}
          style={{ right: insets.right + 16, bottom: insets.bottom + 16 + (44 + 10) * 2 }}
          aria-pressed={streetArmed}
          aria-label={me ? 'Street view: down to eye level where the figure stands' : streetArmed ? 'Cancel street view' : 'Street view: tap here, then where to stand'}
          title={me ? 'Street view · see it from where you stand' : 'Street view · tap, then tap where to stand'}
          onPointerDown={(event) => event.stopPropagation()}
          onPointerUp={(event) => event.stopPropagation()}
          onClick={() => {
            setPlacing(false)
            if (me) enterStreet(me.door ?? me.at, me.floor)
            else setStreetArmed((on) => !on)
          }}
        >
          <Footprints size={20} aria-hidden="true" />
        </button>
      )}
      {streetArmed && (
        <p className="me-hint" style={{ right: insets.right + 16 + 44 + 10, bottom: insets.bottom + 16 + (44 + 10) * 2 }} role="status">
          Tap where to stand · Esc cancels
        </p>
      )}
      {street && streetFloor && (
        <StreetView plan={plan} palette={palette} street={street} insets={insets} route={story.route?.line} compass={headingUp} onClose={() => setStreet(null)}>
          <Lights plan={plan} floors={[street.floor]} palette={palette} lift={noLift} />
          <FloorModel geometry={streetFloor} palette={palette} floor={street.floor} furniture={settings.furniture === 'full'} />
        </StreetView>
      )}
      {placing && (
        <p className="me-hint" style={{ right: insets.right + 16 + 44 + 10, bottom: insets.bottom + 16 }} role="status">
          Tap where you are — off the building for an entrance · Esc cancels
        </p>
      )}
      {onMe && (
        <button
          ref={dock}
          type="button"
          className={`me-dock${me ? ' placed' : ''}${placing ? ' armed' : ''}`}
          style={{ right: insets.right + 16, bottom: insets.bottom + 16 }}
          aria-pressed={placing}
          aria-label={me ? 'Take the figure off the plan' : placing ? 'Cancel putting the figure down' : 'Put the figure where you are: drag it onto the plan, or tap here and then the plan'}
          title={me ? 'Tap to take the figure off · drag to put it somewhere else' : 'Drag me to where you are, or tap me and then the plan'}
          onPointerDown={(event) => {
            event.stopPropagation()
            event.currentTarget.setPointerCapture(event.pointerId)
            dockDrag.current = { x: event.clientX, y: event.clientY, moved: false }
          }}
          onPointerMove={(event) => {
            const drag = dockDrag.current
            if (!drag) return
            if (Math.hypot(event.clientX - drag.x, event.clientY - drag.y) > TAP_SLOP_PX) drag.moved = true
            const box = event.currentTarget.parentElement?.getBoundingClientRect()
            if (drag.moved && box) showGhost(event.clientX - box.left, event.clientY - box.top)
          }}
          onPointerUp={(event) => {
            event.stopPropagation()
            const drag = dockDrag.current
            dockDrag.current = null
            hideGhost()
            if (!drag) return
            const box = event.currentTarget.parentElement?.getBoundingClientRect()
            if (drag.moved) {
              setPlacing(false)
              // let go over the dock itself: nothing happens
              const dockBox = event.currentTarget.getBoundingClientRect()
              const overDock = event.clientX >= dockBox.left && event.clientX <= dockBox.right && event.clientY >= dockBox.top && event.clientY <= dockBox.bottom
              if (box && !overDock) dropMe(event.clientX - box.left, event.clientY - box.top)
            } else if (me) onMe(null)
            else setPlacing((on) => !on) // a tap: the next tap on the plan puts it there
          }}
          onPointerCancel={() => {
            dockDrag.current = null
            hideGhost()
          }}
        >
          <PersonGlyph size={22} />
          {me && <small aria-hidden="true">×</small>}
        </button>
      )}
      {objects && objects.length > 0 && <ObjectMarkers objects={objects} palette={palette} elements={objectElements} />}
    </div>
  )
}

/** an outside wall run in floor-local scene metres, with its outward normal and length */
type WallEdge = { a: THREE.Vector2; b: THREE.Vector2; normal: THREE.Vector2; length: number }
/** where one inscription goes: the wall it is on and the point on it the name centres on, if it fits */
type SignSpot = { edge: WallEdge; point: THREE.Vector2 }
const TAG_LETTERS = 0.7 // letter block height, as a share of the wall height
const TAG_OUT_M = 0.25 + 0.03 // the exterior wall's thickness outside the outline (core/floorplan.py EXTERIOR_M), plus a hair so the letters never flicker into its face

/** The outer walls of a floor, from its outline (else its rooms' bounding box). */
function wallEdges(plan: Plan, floor: number): WallEdge[] {
  const outline = plan.outlines?.[floor] ?? []
  let rings = outline.map((polygon) => polygon[0]?.map(([x, y]) => toScene(plan, x, y)) ?? []).filter((ring) => ring.length > 2)
  if (!rings.length) {
    const box = floorBox(plan, [floor])
    rings = [[[box.min.x, box.min.y], [box.max.x, box.min.y], [box.max.x, box.max.y], [box.min.x, box.max.y]]]
  }
  const edges: WallEdge[] = []
  for (const ring of rings) {
    // winding decides which side of each edge is outside
    let area = 0
    ring.forEach(([x, z], i) => {
      const [nx, nz] = ring[(i + 1) % ring.length]
      area += x * nz - nx * z
    })
    const sign = area > 0 ? 1 : -1
    ring.forEach(([x, z], i) => {
      const [nx, nz] = ring[(i + 1) % ring.length]
      const length = Math.hypot(nx - x, nz - z)
      if (length < 1) return
      edges.push({
        a: new THREE.Vector2(x, z),
        b: new THREE.Vector2(nx, nz),
        normal: new THREE.Vector2((sign * (nz - z)) / length, (sign * -(nx - x)) / length),
        length,
      })
    })
  }
  return edges
}

/** One inscription per side of the floor (east, north, west, south). On each side it sits on the outermost wall
 * crossing the building's centre line, the same line for every floor, so the names stack in one column; a floor
 * with no wall there falls back to its longest wall on that side. */
function signSpots(edges: WallEdge[], centre: THREE.Vector2): SignSpot[] {
  const spots: SignSpot[] = []
  for (let side = 0; side < 4; side++) {
    const facing = edges.filter((edge) => (Math.round(Math.atan2(edge.normal.y, edge.normal.x) / (Math.PI / 2)) & 3) === side)
    if (!facing.length) continue
    const across = side % 2 === 0 ? 'y' : 'x' // east/west walls run along z (Vector2 y), north/south along x
    const out = side % 2 === 0 ? 'x' : 'y'
    const outward = side < 2 ? 1 : -1
    const line = centre[across]
    let best: { point: THREE.Vector2; edge: WallEdge } | null = null
    for (const edge of facing) {
      const [p, q] = [edge.a[across], edge.b[across]]
      if (line < Math.min(p, q) || line > Math.max(p, q) || p === q) continue
      const point = edge.a.clone().lerp(edge.b, (line - p) / (q - p))
      if (!best || point[out] * outward > best.point[out] * outward) best = { point, edge }
    }
    const longest = facing.reduce((a, b) => (b.length > a.length ? b : a))
    spots.push(best ?? { point: longest.a.clone().lerp(longest.b, 0.5), edge: longest })
  }
  return spots
}

/** The stacked view's floor name, cut into the outside walls in big letters: once per side of the floor, all floors
 * in one column (signSpots), readable only from outside (front faces only), so whichever walls face the camera carry it. */
function FloorTag({ plan, floor, name, height, palette, current }: {
  plan: Plan
  floor: number
  name: string
  height: number
  palette: PlanPalette
  current: boolean
}) {
  const invalidate = useThree((state) => state.invalidate)
  const centre = useMemo(() => floorBox(plan, plan.floors.map((_, i) => i)).getCenter(new THREE.Vector2()), [plan])
  const spots = useMemo(() => signSpots(wallEdges(plan, floor), centre), [plan, floor, centre])
  const { texture, aspect } = useMemo(() => {
    const px = 128
    const canvas = document.createElement('canvas')
    const context = canvas.getContext('2d')!
    const font = `800 ${px}px ${FONT}`
    context.font = font
    canvas.width = Math.ceil(context.measureText(name).width + px * 0.5)
    canvas.height = Math.ceil(px * 1.35)
    context.font = font
    context.textAlign = 'center'
    context.textBaseline = 'middle'
    context.lineJoin = 'round'
    const [x, y] = [canvas.width / 2, canvas.height / 2]
    // label-coloured letters in a thick halo rim: readable on the clay wall, the slab or the ground behind
    context.lineWidth = px * 0.2
    context.strokeStyle = palette.halo
    context.strokeText(name, x, y)
    context.fillStyle = current ? palette.selectedEdge : palette.label
    context.fillText(name, x, y)
    const texture = new THREE.CanvasTexture(canvas)
    texture.colorSpace = THREE.SRGBColorSpace
    texture.anisotropy = 4
    return { texture, aspect: canvas.width / canvas.height }
  }, [name, palette, current])
  useEffect(() => () => texture.dispose(), [texture])
  useEffect(() => invalidate(), [texture, spots, invalidate])
  if (!name) return null
  return (
    <>
      {spots.map(({ edge, point }, i) => {
        // as tall as the wall allows, narrowed only if the name is longer than the wall; slid along the wall
        // (out of the column) only as far as it takes to keep clear of the wall's ends
        const letters = Math.min(height * TAG_LETTERS, (edge.length * 0.9) / aspect)
        const half = (letters * aspect) / 2 / edge.length
        const t = THREE.MathUtils.clamp(point.distanceTo(edge.a) / edge.length, half + 0.05, 0.95 - half)
        const on = edge.a.clone().lerp(edge.b, half + 0.05 > 0.95 - half ? 0.5 : t)
        const at = new THREE.Vector3(on.x, height / 2, on.y).add(new THREE.Vector3(edge.normal.x, 0, edge.normal.y).multiplyScalar(TAG_OUT_M))
        return (
          <mesh key={i} position={at} rotation={[0, Math.atan2(edge.normal.x, edge.normal.y), 0]} renderOrder={3}>
            <planeGeometry args={[letters * aspect, letters]} />
            <meshBasicMaterial map={texture} transparent depthWrite={false} toneMapped={false} />
          </mesh>
        )
      })}
    </>
  )
}

const noLift = () => 0

/** Street view's first heading at a point (camera yaw): along the route, if the route passes within reach on that
 * floor, the way it goes on from its nearest point (plan +y is scene -Z; yaw 0 looks along -Z). */
function streetYaw(line: [number, number, number][] | undefined, [x, y]: [number, number], floor: number): number | null {
  if (!line) return null
  let nearest = -1
  let away = 4 // metres
  line.forEach(([px, py, at], i) => {
    const d = Math.hypot(px - x, py - y)
    if (at === floor && d < away) [nearest, away] = [i, d]
  })
  if (nearest < 0) return null
  const next = line.slice(nearest + 1).find(([px, py, at]) => at === floor && Math.hypot(px - line[nearest][0], py - line[nearest][1]) > 0.3)
  if (!next) return null
  return Math.atan2(-(next[0] - line[nearest][0]), next[1] - line[nearest][1])
}

function disposeFloor(floor: FloorGeometry) {
  for (const geometry of [floor.fills, floor.slab, floor.walls, floor.shade, floor.lines, floor.outline, floor.doors, floor.wallEdges, floor.furnitureEdges, floor.contact, floor.furniture]) geometry.dispose()
}

/** the point on a polygon's edge nearest to a point, and how far it is (metres) */
function nearestEdge(polygon: [number, number][], [x, y]: [number, number]): { at: [number, number]; away: number } {
  let best = { at: [x, y] as [number, number], away: Infinity }
  for (let i = 0; i < polygon.length; i++) {
    const [ax, ay] = polygon[i]
    const [bx, by] = polygon[(i + 1) % polygon.length]
    const [dx, dy] = [bx - ax, by - ay]
    const t = Math.max(0, Math.min(1, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy || 1)))
    const at: [number, number] = [ax + t * dx, ay + t * dy]
    const away = Math.hypot(at[0] - x, at[1] - y)
    if (away < best.away) best = { at, away }
  }
  return best
}

const groundIndex = (plan: Plan) => Math.max(0, plan.floors.findIndex((item) => item.level === 0))

/** Everything drawn relative to the current floor. When the floor changes, the whole stack starts where it was
 * and slides into place, so you see yourself going up or down. Stepping into or out of the stack works the same
 * way: the floor you land on starts where it was drawn, so it never jumps. */
function Slide({ floor, mode, lift, heightOf, children }: {
  floor: number
  mode: 'stacked' | 'floor'
  lift: (index: number) => number
  heightOf: (index: number) => number
  children: React.ReactNode
}) {
  const group = useRef<THREE.Group>(null)
  const previous = useRef({ floor, mode, lift })
  const invalidate = useThree((state) => state.invalidate)
  useLayoutEffect(() => {
    const node = group.current
    const was = previous.current
    previous.current = { floor, mode, lift }
    if (!node) return
    // keep any slide still in progress, so a quick second switch carries on from where things are on screen
    if (mode !== was.mode) node.position.y += was.lift(floor) - lift(floor)
    else if (mode === 'floor' && floor !== was.floor) node.position.y = heightOf(floor) - heightOf(was.floor)
    else return
    invalidate()
  }, [floor, mode, lift, heightOf, invalidate])
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
function Ground({ plan, palette, y, visible, mesh }: { plan: Plan; palette: PlanPalette; y: number; visible: boolean; mesh: React.RefObject<THREE.Mesh | null> }) {
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
    <mesh ref={mesh} position={[centre.x, y, centre.y]} rotation={[-Math.PI / 2, 0, 0]} material={material} renderOrder={-2} visible={visible}>
      <planeGeometry args={[600, 600]} />
    </mesh>
  )
}

const SHELL_CORNER_DEG = 25 // a wireframe corner gets its upright edge when the outline turns at least this much

/** The building in its city, drawn with the model so both share one depth: the map's own blocks of it as a wireframe
 * (the map leaves them out, src/map/bridge.ts) and the ground floor's outline as a line where it meets the ground. */
function City({ plan, palette, y, shell }: { plan: Plan; palette: PlanPalette; y: number; shell: ShellBlock[] }) {
  const invalidate = useThree((state) => state.invalidate)
  const wireframe = useMemo(() => {
    const points: number[] = []
    const at = (x: number, height: number, z: number) => points.push(x, height, z)
    for (const block of shell)
      for (const ring of block.rings) {
        const scene = ring.map(([x, yy]) => toScene(plan, x, yy))
        const n = scene.length - (scene.length > 1 && scene[0][0] === scene[scene.length - 1][0] && scene[0][1] === scene[scene.length - 1][1] ? 1 : 0)
        for (let i = 0; i < n; i++) {
          const [ax, az] = scene[i]
          const [bx, bz] = scene[(i + 1) % n]
          for (const height of [block.base, block.top]) {
            at(ax, height, az)
            at(bx, height, bz)
          }
          const [px, pz] = scene[(i - 1 + n) % n]
          const turn = Math.abs(Math.atan2((ax - px) * (bz - az) - (az - pz) * (bx - ax), (ax - px) * (bx - ax) + (az - pz) * (bz - az)))
          if (THREE.MathUtils.radToDeg(turn) >= SHELL_CORNER_DEG) {
            at(ax, block.base, az)
            at(ax, block.top, az)
          }
        }
      }
    const geometry = new THREE.BufferGeometry()
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(points, 3))
    return geometry
  }, [plan, shell])
  const footprint = useMemo(() => {
    const points: number[] = []
    for (const polygon of plan.outlines?.[groundIndex(plan)] ?? []) {
      const ring = polygon[0] ?? []
      ring.forEach(([x, yy], i) => {
        const [nx, ny] = ring[(i + 1) % ring.length]
        points.push(...[toScene(plan, x, yy), toScene(plan, nx, ny)].flatMap(([sx, sz]) => [sx, 0, sz]))
      })
    }
    const geometry = new THREE.BufferGeometry()
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(points, 3))
    return geometry
  }, [plan])
  const lineMaterials = useMemo(
    () => ({
      shell: new THREE.LineBasicMaterial({ color: palette.labelSoft, transparent: true, opacity: 0.55 }),
      footprint: new THREE.LineBasicMaterial({ color: palette.labelSoft, transparent: true, opacity: 0.9 }),
    }),
    [palette.labelSoft],
  )
  useEffect(() => () => wireframe.dispose(), [wireframe])
  useEffect(() => () => footprint.dispose(), [footprint])
  useEffect(() => () => Object.values(lineMaterials).forEach((material) => material.dispose()), [lineMaterials])
  useEffect(() => invalidate(), [wireframe, invalidate])
  return (
    <group position={[0, y, 0]}>
      <lineSegments geometry={wireframe} material={lineMaterials.shell} />
      <lineSegments geometry={footprint} material={lineMaterials.footprint} position={[0, 0.02, 0]} />
    </group>
  )
}

/** Every floor outline the drawing has: the spaces, plus the restricted ones (access mode) drawn without detail. */
const drawnShapes = (plan: Plan): { floor: number; polygon: [number, number][] }[] =>
  plan.restricted?.length ? [...plan.spaces, ...plan.restricted] : plan.spaces

function floorBox(plan: Plan, floors: number[]) {
  const box = new THREE.Box2()
  for (const space of drawnShapes(plan)) {
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
const UNDER_TINT = 0.35 // a basement you are not on: its colours times this, so it reads as under the street
const UNDER_FADED_OPACITY = 0.3 // a darkened basement under the current floor: a bit more there, or the dark won't read

function FloorModel({ geometry, palette, floor, furniture, faded = false, under = false }: {
  geometry: FloorGeometry
  palette: PlanPalette
  floor: number
  furniture: boolean
  faded?: boolean
  under?: boolean
}) {
  const invalidate = useThree((state) => state.invalidate)
  const shade = useMemo(() => shadeMaterial(palette.ao), [palette.ao])
  useEffect(() => () => shade.dispose(), [shade])
  useEffect(() => invalidate(), [geometry, faded, under, invalidate])
  // a basement you are not on is drawn darker: vertex colours and the plain colours times UNDER_TINT
  const tint = (colour: THREE.ColorRepresentation = 0xffffff) => (under ? new THREE.Color(colour).multiplyScalar(UNDER_TINT) : colour)
  // see-through for floors above: every material at FADED_OPACITY, no depth writes, no shadows, not pickable
  const fade = (opacity = 1) => (faded ? { transparent: true, opacity: opacity * (under ? UNDER_FADED_OPACITY : FADED_OPACITY), depthWrite: false } : { transparent: opacity < 1, opacity })
  const solid = !faded

  return (
    <group key={faded ? 'faded' : 'solid'}>
      <mesh geometry={geometry.fills} receiveShadow={solid}>
        <meshLambertMaterial vertexColors color={tint()} side={THREE.DoubleSide} {...fade()} />
      </mesh>
      <mesh geometry={geometry.slab}>
        <meshLambertMaterial color={tint(palette.slab)} side={THREE.DoubleSide} {...fade()} />
      </mesh>
      {solid && <mesh geometry={geometry.shade} material={shade} renderOrder={1} />}
      {solid && furniture && <mesh geometry={geometry.contact} material={shade} renderOrder={1} />}
      <lineSegments geometry={geometry.lines} renderOrder={2}>
        <lineBasicMaterial color={tint(palette.hairline)} {...fade(0.8)} />
      </lineSegments>
      <mesh geometry={geometry.walls} castShadow={solid} receiveShadow={solid}>
        <meshLambertMaterial vertexColors color={tint()} side={THREE.DoubleSide} polygonOffset polygonOffsetFactor={1} polygonOffsetUnits={1} {...fade()} />
      </mesh>
      <lineSegments geometry={geometry.wallEdges}>
        <lineBasicMaterial color={tint(palette.edge)} {...fade()} />
      </lineSegments>
      {solid && (
        <mesh geometry={geometry.doors} renderOrder={2}>
          <meshBasicMaterial vertexColors color={tint()} side={THREE.DoubleSide} />
        </mesh>
      )}
      {/* floors above show only their shell: furniture of two see-through floors on top of each other is noise */}
      {furniture && solid && (
        <>
          <mesh geometry={geometry.furniture} castShadow={solid} receiveShadow={solid} userData={solid ? { furnitureFloor: floor } : {}}>
            <meshLambertMaterial vertexColors color={tint()} side={THREE.DoubleSide} polygonOffset polygonOffsetFactor={1} polygonOffsetUnits={1} {...fade()} />
          </mesh>
          <lineSegments geometry={geometry.furnitureEdges}>
            <lineBasicMaterial color={tint(palette.edge)} {...fade(0.55)} />
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

/** The floor under the mouse in the stacked view: its floor washed with the selection colour, its walls and slab
 * edge drawn in the selection's edge colour. */
function FloorGlow({ geometry, palette }: { geometry: FloorGeometry; palette: PlanPalette }) {
  const invalidate = useThree((state) => state.invalidate)
  useEffect(() => {
    invalidate()
    return () => invalidate()
  }, [geometry, invalidate])
  return (
    <group renderOrder={4}>
      <mesh geometry={geometry.fills} position={[0, 0.03, 0]} renderOrder={4}>
        <meshBasicMaterial color={palette.selected} transparent opacity={0.45} depthWrite={false} side={THREE.DoubleSide} toneMapped={false} />
      </mesh>
      <mesh geometry={geometry.slab} renderOrder={4}>
        <meshBasicMaterial color={palette.selectedEdge} transparent opacity={0.8} depthWrite={false} side={THREE.DoubleSide} toneMapped={false} />
      </mesh>
      <lineSegments geometry={geometry.outline} position={[0, 0.04, 0]} renderOrder={5}>
        <lineBasicMaterial color={palette.selectedEdge} depthWrite={false} />
      </lineSegments>
    </group>
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
  for (const space of drawnShapes(plan)) {
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

/** Camera framing for a few points ([X, Z, height] in the scene): the zoom that fits them, grown to at least `span`
 * metres across so a small room keeps its neighbours around it, centred in the free part of the screen. */
function fitPoints(points: [number, number, number][], view: { polar: number; azimuth: number }, size: { width: number; height: number }, insets: Insets, span: number) {
  const probe = new THREE.OrthographicCamera()
  probe.position.copy(offsetFor(view.polar, view.azimuth))
  probe.up.set(0, 1, 0)
  probe.lookAt(0, 0, 0)
  probe.updateMatrixWorld()
  const inverse = probe.matrixWorldInverse
  const extent = new THREE.Box2()
  const p = new THREE.Vector3()
  const box = new THREE.Box2()
  for (const [X, Z, height] of points) {
    box.expandByPoint(new THREE.Vector2(X, Z))
    for (const h of [height, height + WALL_CUT_M]) {
      p.set(X, h, Z).applyMatrix4(inverse)
      extent.expandByPoint(new THREE.Vector2(p.x, p.y))
    }
  }
  const mid = extent.getCenter(new THREE.Vector2())
  extent.expandByPoint(new THREE.Vector2(mid.x - span / 2, mid.y - span / 2)).expandByPoint(new THREE.Vector2(mid.x + span / 2, mid.y + span / 2))
  const free = {
    width: Math.max(80, size.width - insets.left - insets.right - FIT_MARGIN_PX * 2),
    height: Math.max(80, size.height - insets.top - insets.bottom - FIT_MARGIN_PX * 2),
  }
  const extentSize = extent.getSize(new THREE.Vector2())
  const zoom = Math.min(MAX_ZOOM, free.width / Math.max(extentSize.x, 1), free.height / Math.max(extentSize.y, 1))
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
  if (Math.abs(forward.y) > 1e-6) target.addScaledVector(forward, -target.y / forward.y)
  return { target, zoom }
}

/** The model rising out of the ground the first time it is drawn (the walls grow up from the floor). */
function Reveal({ children }: { children: React.ReactNode }) {
  const group = useRef<THREE.Group>(null)
  const t = useRef(0)
  const invalidate = useThree((state) => state.invalidate)
  useLayoutEffect(() => {
    if (group.current && t.current < 1) group.current.scale.y = 0.001
  }, [])
  useFrame((_, delta) => {
    const node = group.current
    if (!node || t.current >= 1) return
    t.current = Math.min(1, t.current + Math.min(delta, 1 / 30) / REVEAL_SECONDS)
    node.scale.y = Math.max(0.001, 1 - Math.pow(1 - t.current, 3))
    invalidate()
  })
  return <group ref={group}>{children}</group>
}

/** Hands the camera to the map under the model on every frame that moved it: the ground point at the centre of
 * the screen (on the model's own ground), the zoom as pixels per metre, the tilt and the turn. */
function Follow({ plan, ground, follow }: { plan: Plan; ground: React.RefObject<THREE.Mesh | null>; follow?: (view: View) => void }) {
  const camera = useThree((state) => state.camera) as THREE.OrthographicCamera
  const invalidate = useThree((state) => state.invalidate)
  const sent = useRef('')
  const scratch = useMemo(() => ({ ground: new THREE.Vector3(), look: new THREE.Vector3(), at: new THREE.Vector3() }), [])
  useEffect(() => {
    sent.current = ''
    invalidate()
  }, [follow, invalidate])
  useEffect(() => {
    if (import.meta.env.DEV) Object.assign(window, { __plan: { camera, ground, plan } }) // alignment checks
  }, [camera, ground, plan])
  useFrame(() => {
    if (!follow) return
    const { look, at } = scratch
    const groundY = ground.current?.getWorldPosition(scratch.ground).y ?? 0
    camera.getWorldDirection(look)
    if (Math.abs(look.y) < 1e-6) return
    at.copy(camera.position).addScaledVector(look, (groundY - camera.position.y) / look.y)
    const [x, y] = fromScene(plan, at.x, at.z)
    const view: View = {
      x,
      y,
      scale: camera.zoom,
      pitch: THREE.MathUtils.radToDeg(Math.acos(THREE.MathUtils.clamp(-look.y, -1, 1))),
      bearing: THREE.MathUtils.radToDeg(Math.atan2(look.x, -look.z)),
    }
    const key = `${x.toFixed(3)},${y.toFixed(3)},${view.scale.toFixed(4)},${view.pitch.toFixed(3)},${view.bearing.toFixed(3)}`
    if (key === sent.current) return
    sent.current = key
    follow(view)
  })
  return null
}

const COMPASS_TICKS = Array.from({ length: 11 }, (_, index) => (index + 1) * 30) // every 30°, none under the N

/** Turns the compass rose with the camera on every frame: the camera's azimuth is minus its bearing (degrees
 * clockwise from north), and north sits that far round on the screen. */
function CompassTracker({ rose, azimuth: turn }: { rose: React.RefObject<HTMLSpanElement | null>; azimuth: React.RefObject<number> }) {
  const controls = useThree((state) => state.controls) as MapControlsImpl | null
  const last = useRef(NaN)
  useFrame(() => {
    const node = rose.current
    if (!node || !controls) return
    const azimuth = controls.getAzimuthalAngle()
    if (azimuth === last.current) return
    last.current = azimuth
    turn.current = azimuth
    node.style.setProperty('--turn', `${azimuth}rad`)
  })
  return null
}

type Pose = { target: THREE.Vector3; zoom: number; polar: number; azimuth: number }
type Move = { t: number; from: Pose; to: Pose; seconds?: number }

/** Frames the shown floors (tilted, or flat if the user went flat on one floor) whenever they or fitKey change, easing there. Tilting is free in between
 * (0 = straight down … MAX_POLAR); a nearly flat tilt snaps flat when the gesture ends, and the current look
 * (flat or tilted) is reported so a flat view can stop spreading the floors. */
function Rig({ plan, floor, floors, stacked, frameInsets, focusInsets, fitKey, focus, onTilt, intro, ground, maxPolar, northUp, headingUp, onNoCompass }: {
  plan: Plan
  floor: number
  floors: number[]
  stacked: boolean
  frameInsets: Insets
  focusInsets: Insets
  fitKey: number
  focus: Focus | null
  onTilt: (mode: ViewMode) => void
  /** the camera to start from (the map's), eased from to the first framing */
  intro?: () => View | null
  ground: React.RefObject<THREE.Mesh | null>
  maxPolar: number
  /** filled in here: eases the camera round until north is up, keeping where it looks, its zoom and its tilt */
  northUp: React.RefObject<(() => void) | null>
  /** turn with the phone's compass: the way it faces stays up (where it looks, its zoom and tilt stay the user's) */
  headingUp: boolean
  onNoCompass: () => void
}) {
  const camera = useThree((state) => state.camera) as THREE.OrthographicCamera
  const size = useThree((state) => state.size)
  const invalidate = useThree((state) => state.invalidate)
  const controls = useThree((state) => state.controls) as MapControlsImpl | null
  // Insets are read when a fit happens, not watched: the sheet moving must not move the map.
  const insetsRef = useRef(focusInsets)
  insetsRef.current = focusInsets
  const frameInsetsRef = useRef(frameInsets)
  frameInsetsRef.current = frameInsets
  const onTiltRef = useRef(onTilt)
  onTiltRef.current = onTilt
  const stackedRef = useRef(stacked)
  stackedRef.current = stacked
  const move = useRef<Move | null>(null)
  const first = useRef(true)
  const heading = useRef<number | null>(null) // the compass reading heading-up turns to (degrees)
  const onNoCompassRef = useRef(onNoCompass)
  onNoCompassRef.current = onNoCompass
  // what the last framing was for, and whether the user has moved the camera since: a resize alone (the phone's
  // address bar, a panel opening) reframes only a view the user has not touched, so it never throws away theirs
  const framedFor = useRef<string | null>(null)
  const touched = useRef(false)
  const reported = useRef<ViewMode | null>(null)
  // only what is framed: the whole stack refits when its floors change; one floor at a time never refits on a floor
  // change (the camera stays where you put it, the floors slide past it), nor when the plan object is replaced by
  // the same building (an edit in the Edit mode: same id, same centre)
  const key = stacked ? floors.join(',') : 'floor'
  const planKey = `${plan.building.id}|${plan.center.join(',')}`

  const report = (polar: number) => {
    const mode: ViewMode = polar < FLAT_BELOW ? '2d' : '3d'
    if (mode !== reported.current) {
      reported.current = mode
      onTiltRef.current(mode)
    }
  }

  // the height the pivot was framed at: panning and zooming to the cursor move the camera in the screen's plane,
  // which (tilted) carries the pivot up or down off the floor, and a turn then swings round a point in mid-air
  const pivotY = useRef<number | null>(null)

  const place = (pose: Pose) => {
    if (!controls) return
    pivotY.current = pose.target.y
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
    const look = new THREE.Vector3()
    // slide the pivot (and the camera with it) along the line of sight back to its height: an orthographic view
    // looks the same from anywhere on that line, so only what a turn pivots round changes
    const onChange = () => {
      const y = pivotY.current
      if (y === null) return
      look.subVectors(controls.target, camera.position)
      if (Math.abs(look.y) < 1e-6) return
      const drift = (y - controls.target.y) / look.y
      if (Math.abs(drift * look.y) < 1e-6) return
      look.multiplyScalar(drift)
      controls.target.add(look)
      camera.position.add(look)
      camera.updateMatrixWorld()
    }
    controls.addEventListener('change', onChange)
    return () => controls.removeEventListener('change', onChange)
  }, [controls, camera])

  useEffect(() => {
    heading.current = null
    if (!headingUp) return
    let heard = false
    const stop = watchCompass((reading) => {
      heard = true
      heading.current = reading.heading
      invalidate()
    })
    const timer = setTimeout(() => !heard && onNoCompassRef.current(), COMPASS_WAIT_MS)
    return () => {
      stop()
      clearTimeout(timer)
    }
  }, [headingUp, invalidate])

  useEffect(() => {
    northUp.current = () => {
      if (!controls) return
      const from = { target: controls.target.clone(), zoom: camera.zoom, polar: controls.getPolarAngle(), azimuth: controls.getAzimuthalAngle() }
      move.current = { t: 0, from, to: { ...from, target: from.target.clone(), azimuth: 0 } } // azimuth 0 looks along -Z, the plan's north
      invalidate()
    }
    return () => void (northUp.current = null)
  }, [northUp, controls, camera, invalidate])

  const trigger = `${planKey}|${key}|${stacked}|${fitKey}|${focus?.key ?? ''}`
  useEffect(() => {
    if (!controls) return
    if (!first.current && trigger === framedFor.current && touched.current) return
    framedFor.current = trigger
    touched.current = false
    // keep the user's own turn, unless the answer faces a way (plan +y is scene -Z; azimuth 0 looks along -Z)
    const heading = first.current ? undefined : focus?.heading
    const azimuth = first.current ? TILTED.azimuth : heading ? Math.atan2(-heading[0], heading[1]) : controls.getAzimuthalAngle()
    // and the user's own tilt (the whole stack is only readable tilted: a flat look goes back to the default tilt)
    const polar = first.current ? TILTED.polar : stacked && reported.current === '2d' ? TILTED.polar : controls.getPolarAngle()
    // the whole stack, or the floor you are on: the camera focuses on your floor; the others stay spread
    // above and below it, out of frame until you zoom out
    const framed = stacked ? floors : [floor]
    const lift = (i: number) => (stacked ? floorLift(plan, i) : 0)
    // an answer's own points, where they are on what is shown (not on the very first framing: the building comes first)
    const points = first.current ? [] : focus?.points.filter(([, , at]) => framed.includes(at)) ?? []
    const fit = points.length
      ? fitPoints(points.map(([x, y, at]) => [...toScene(plan, x, y), lift(at)] as [number, number, number]), { polar, azimuth }, size, insetsRef.current, focus?.span ?? 0)
      : frame(plan, framed, lift, { polar, azimuth }, size, frameInsetsRef.current)
    const to = { target: fit.target, zoom: fit.zoom, polar, azimuth }
    if (first.current) {
      first.current = false
      const start = intro?.()
      if (start) {
        // the map's camera, on the map's ground under the model
        const [X, Z] = toScene(plan, start.x, start.y)
        const y = ground.current?.getWorldPosition(new THREE.Vector3()).y ?? 0
        const from = { target: new THREE.Vector3(X, y, Z), zoom: start.scale, polar: Math.max(FLAT_POLAR, THREE.MathUtils.degToRad(start.pitch)), azimuth: -THREE.MathUtils.degToRad(start.bearing) }
        place(from)
        controls.update()
        move.current = { t: 0, from, to, seconds: INTRO_SECONDS }
        invalidate()
        return
      }
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
  }, [trigger, controls, size.width, size.height, camera, invalidate])

  useFrame((_, delta) => {
    const current = move.current
    // heading-up between camera moves: ease the turn toward the phone, keeping where it looks, its zoom and tilt
    if (!current && controls && heading.current !== null) {
      const azimuth = controls.getAzimuthalAngle()
      const turn = shortest(azimuth, turnFor(heading.current))
      if (Math.abs(turn) > 1e-3) {
        const k = 1 - Math.exp(-HEADING_RATE * Math.min(delta, 1 / 30))
        place({ target: controls.target.clone(), zoom: camera.zoom, polar: controls.getPolarAngle(), azimuth: azimuth + turn * k })
        invalidate()
      }
    }
    if (!current || !controls) return
    // on-demand rendering: the first frame's delta is the whole idle time before it, so cap the step
    current.t = Math.min(1, current.t + Math.min(delta, 1 / 30) / (current.seconds ?? MOVE_SECONDS))
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
    touched.current = true
  }, [])

  return (
    <MapControls
      makeDefault
      enableDamping={false}
      screenSpacePanning
      minZoom={1}
      maxZoom={MAX_ZOOM}
      minPolarAngle={FLAT_POLAR}
      maxPolarAngle={maxPolar}
      zoomToCursor
      onStart={onStart}
    />
  )
}

/** Screen point → what is under it: a piece of furniture first, else the smallest space on that floor (rooms win
 * over the hall around them). With floors stacked, the floor nearest the camera wins. */
/** Keeps an SVG group in building metres on top of the floor plane at height `y`: projects the plane's origin and
 * its x / y unit points every frame and writes them as the group's matrix (only when it changed). */
function Align({ plan, y, target }: { plan: Plan; y: number; target: React.RefObject<SVGGElement | null> }) {
  const scratch = useMemo(() => [new THREE.Vector3(), new THREE.Vector3(), new THREE.Vector3()], [])
  const last = useRef('')
  useFrame(({ camera, size }) => {
    const group = target.current
    if (!group) return
    camera.updateMatrixWorld()
    const screen = ([x, yy]: [number, number], into: THREE.Vector3) => {
      const [sx, sz] = toScene(plan, x, yy)
      into.set(sx, y, sz).project(camera)
      return [((into.x + 1) / 2) * size.width, ((1 - into.y) / 2) * size.height]
    }
    const [ox, oy] = screen([0, 0], scratch[0])
    const [xx, xy] = screen([1, 0], scratch[1])
    const [yx, yy] = screen([0, 1], scratch[2])
    const matrix = `matrix(${xx - ox} ${xy - oy} ${yx - ox} ${yy - oy} ${ox} ${oy})`
    if (matrix === last.current) return
    last.current = matrix
    group.setAttribute('transform', matrix)
    group.dispatchEvent(new Event('aligned'))
  })
  return null
}

function Picker({ plan, floors, lift, stacked, geometries, pick, unproject, zoom }: {
  plan: Plan
  floors: number[]
  lift: (index: number) => number
  stacked: boolean
  geometries: FloorGeometry[]
  pick: React.RefObject<(x: number, y: number) => Hit | null>
  unproject: React.RefObject<(x: number, y: number, floor: number) => [number, number] | null>
  zoom: React.RefObject<() => number>
}) {
  const { camera, size, scene } = useThree()
  useEffect(() => {
    const raycaster = new THREE.Raycaster()
    zoom.current = () => (camera as THREE.OrthographicCamera).zoom
    unproject.current = (x: number, y: number, floor: number) => {
      raycaster.setFromCamera(new THREE.Vector2((x / size.width) * 2 - 1, -(y / size.height) * 2 + 1), camera)
      const point = raycaster.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0, 1, 0), -lift(floor)), new THREE.Vector3())
      return point ? fromScene(plan, point.x, point.z) : null
    }
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
  }, [plan, floors, lift, stacked, geometries, camera, size, scene, pick, unproject, zoom])
  return null
}

const FONT = '-apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'
const NAME_PX = 12
const REF_PX = 11
const SMALL_PX = 10 // zoomed out: a label that does not fit its room shrinks to this (the number alone if it has one)
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

function LabelPainter({ plan, floor, stacked, rooms, palette, canvas, selected, skip }: {
  skip: Set<string>
  /** room names; off in the stacked view */
  rooms: boolean
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
  const invalidate = useThree((state) => state.invalidate)
  useEffect(() => invalidate(), [order, palette, stacked, rooms, invalidate])

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

    if (!rooms) return

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
      const [fullName, ref] = labelParts(space)
      const isSelected = space.id === selectedSpace
      context.font = `600 ${NAME_PX}px ${FONT}`
      // the whole name when it fits the room; zoomed out, a smaller label — the room's number if it has one, else its
      // name — that may run past the walls: a room keeps its label until it would cover another one
      const fits = isSelected || (context.measureText(fullName).width <= freeWidth && freeHeight >= NAME_PX + 2)
      const name = fits ? fullName : ref || fullName
      const namePx = fits ? NAME_PX : SMALL_PX
      context.font = `600 ${namePx}px ${FONT}`
      const nameWidth = context.measureText(name).width
      const showRef = fits && Boolean(ref) && freeHeight > NAME_PX + REF_PX + LABEL_GAP_PX + 8
      const height = showRef ? NAME_PX + REF_PX + LABEL_GAP_PX : namePx
      const box: [number, number, number, number] = [sx - nameWidth / 2 - 3, sy - height / 2 - 2, sx + nameWidth / 2 + 3, sy + height / 2 + 2]
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
