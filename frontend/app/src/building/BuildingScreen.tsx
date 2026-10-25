// The building screen: the model fills the screen and a thin HUD sits on top. Top: back, the building and floor,
// a floor chip (with "all floors" stacked) and a menu (edit, fit, theme, dev tools). Bottom: the Guide, voice first —
// captions and the Core (src/building/Guide.tsx). One backend session per building; the plan comes from
// GET /sessions/{id}/plan.
// A building with a place on the map (`origin`) sits on the landing map, which follows the model's camera
// (src/map/bridge.ts): shown in its city (neighbours and their pins around it, a tap on a pin opens that one) or
// alone (the map faded out, the model on its own stage). The model takes over from the map's camera when it
// arrives and rises out of the ground; leaving fades it out.
// Answers move the camera to what they are about (`focus`): the rooms and items found, or a route — every floor
// stacked first when it crosses floors, then one step at a time once the user starts it; each step is read aloud
// and waits for "I'm there". The "you are here" figure tells the Guide where the user is. A route on to a nearby
// building ends in a Continue that opens that building and carries on there (arrival via sessionStorage).

import { Box, Check, ChevronLeft, ChevronsUpDown, Ellipsis, KeyRound, Layers, LogIn, LogOut, Map as MapIcon, Moon, PencilRuler, Scan, Settings2, SlidersHorizontal, Sun, SunMoon, Wrench } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { notify, openPanel, signOut, useAccess } from '../access/auth'
import { BuildingSettings } from '../access/BuildingSettings'
import { capture, effective, usePreferences } from '../access/preferences'
import { api, ApiError, ServiceError, type FleetObject, type Issue, type NextBuilding, type Plan } from '../api'
import { EditLayer } from '../edit/EditLayer'
import { EditBar } from '../edit/EditBar'
import { EditCard } from '../edit/EditCard'
import { useDraft } from '../edit/useDraft'
import { CATEGORY_LABEL, DARK, LIGHT } from '../plan/palette'
import { PlanView, type Focus, type Insets, type Me, type Selected, type ViewMode } from '../plan/PlanView'
import { DEFAULT_SETTINGS } from '../plan/settings'
import { DevPanel, type LogEntry } from '../dev/DevPanel'
import { devApi, type DevEvent } from '../dev/devApi'
import { routeRuns } from '../dev/StoryLayer'
import { applyEvents, EMPTY_STORY, type Outdoor, type Story } from '../dev/story'
import { addStep, settle, type Step } from '../ui/guideSteps'
import { follow, fromLngLat, hideBlocks, mapView, onShell, pinAt, settled, showBlocks, type Origin, type ShellBlock } from '../map/bridge'
import { groundColour } from '../map/style'
import { useTheme } from '../theme'
import { setScribeSession } from '../voice/scribe'
import type { Speech } from '../voice/tts'
import { useVoice, voiceSupported } from '../voice/useVoice'
import { Guide, type InfoCard, type Message, type Suggestion } from './Guide'
import { CameraWalk } from './CameraWalk'
import { grabFrame } from './frame'
import { Elsewhere } from './Elsewhere'
import { NextMove } from './NextMove'
import { take } from './opening'
import { routeTrack, type RouteTrack } from './tracking'
import { askForMotion, useTracking } from './useTracking'
import './screen.css'
import './hud.css'

const WIDE_PX = 900
const TOP_PX = 64 // the HUD line
const GUIDE_PX = 250 // captions + Core on phones
const EDIT_PX = 330 // the Builder card with an inspector in it, on phones
const EDIT_BAR_PX = 52 // the edit bar under the top line on phones (src/edit/edit.css .edit-bar)
const PANEL_PX = 440 // the Guide panel on wide screens
const RAIL_PX = 72 // the floor rail on the right edge of a wide screen, with its margin
const MOVE_PX = 132 // the next-move card under the top line on phones
const TRACK_PX = 30 // its position line while tracking
// spoken commands while walking with the camera (anything else goes to the Guide with the frame)
const NEXT = /^\s*(next|weiter|nächste|sonraki|ileri|done|okay|ok|tamam|geldim|vardım|arrived|i'?m there|i'?m here|here|da|angekommen)\b/i
// starting the step-by-step guide of a route that is on the map
const START = /^\s*(start|go|let'?s go|begin|başla|basla|hadi|yola çık|los|starten)\b/i
// … also inside a short sentence ("okay, start the guide"), but not "start from the lobby"
const START_SAID = /\b(?:(?:start|begin)\b(?!\s+(?:from|at|in|with)\b)|let'?s go\b|başla|yola çık|starten\b)/i
const BACK = /^\s*(back|previous|zurück|geri|önceki)\b/i
const REPEAT = /^\s*(repeat|again|wiederholen|nochmal|tekrar)\b/i
const WHERE_AM_I = 'Where am I? Use what my camera sees.'
/** the Edit mode's assistant in the Guide's card (agent/builder.py) */
const BUILDER = {
  who: 'Builder',
  greeting: <>Tell me what to change. <em>Or tap a room, door or item.</em></>,
  placeholder: 'Describe a change',
}

const useViewport = () => {
  const [size, setSize] = useState({ width: innerWidth, height: innerHeight })
  useEffect(() => {
    const onResize = () => setSize({ width: innerWidth, height: innerHeight })
    addEventListener('resize', onResize)
    return () => removeEventListener('resize', onResize)
  }, [])
  return size
}

const floorTab = (level: number) => (level < 0 ? `B${-level}` : level === 0 ? 'G' : String(level))
const humanise = (type: string) => type.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())
const THEME_ICON = { system: SunMoon, light: Sun, dark: Moon }
const THEME_LABEL = { system: 'Theme: system', light: 'Theme: light', dark: 'Theme: dark' }

/** Shown once as the first chat line when a building opens right after it was saved in the Edit mode. */
const noteKey = (buildingId: string) => `note:${buildingId}`
/** A route coming over from a nearby building (route_to_building → Continue), picked up when this one opens. */
const arrivalKey = (buildingId: string) => `arrival:${buildingId}`
type Arrival = { entrance: string; destination: string; from: string | null; fromName: string; name: string; destinationName: string }
const STEP_WAIT_MS = 45_000 // the step-by-step guide listens this long for "I'm there" while the user walks
const FOCUS_ROOM_M = 14 // a found room is framed at least this wide, so its neighbours show around it
const FOCUS_STEP_M = 12
const FOCUS_ROUTE_M = 10

/** how a building with a place on the map is shown: in its city, or on its own */
export type Showing = 'city' | 'alone'

type ScreenProps = {
  buildingId: string
  /** where the building's metres start on the map, when the map is under this screen */
  origin: Origin | null
  showing: Showing
  onShowing: (showing: Showing) => void
  /** fading out (another building, or the landing, is coming) */
  leaving: boolean
  onBack: () => void
  onOpen: (buildingId: string) => void
}

export function BuildingScreen({ buildingId, origin, showing, onShowing, leaving, onBack, onOpen }: ScreenProps) {
  const theme = useTheme()
  const palette = theme.dark ? DARK : LIGHT
  const viewport = useViewport()
  const wide = viewport.width >= WIDE_PX

  const [sessionId, setSessionId] = useState<string | null>(null)
  const [plan, setPlan] = useState<Plan | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [floor, setFloor] = useState(0)
  const [stacked, setStacked] = useState(false)
  const [selected, setSelected] = useState<Selected | null>(null)
  const [messages, setMessages] = useState<Message[]>(() => {
    const note = sessionStorage.getItem(noteKey(buildingId))
    return note ? [{ role: 'note', text: note }] : []
  })
  const [editing, setEditing] = useState(false)
  // Edit mode (src/edit/): the model becomes the draft copy's, handles sit on it, the edit card takes the Guide's place
  const draft = useDraft(buildingId, editing)
  const align = useRef<SVGGElement>(null)
  // a request the Guide handed over with open_edit_mode, sent to the Builder once the draft is open
  const handOver = useRef<{ text: string; spoken: boolean } | null>(null)
  const [pending, setPending] = useState(false)
  const [popover, setPopover] = useState<'floors' | 'menu' | null>(null)
  // access mode (src/access/): who is signed in, and the building settings sheet (admin)
  const access = useAccess()
  const [settingsOpen, setSettingsOpen] = useState(false)
  const preferences = usePreferences()
  const [objects, setObjects] = useState<FleetObject[]>([])
  const pollNow = useRef<() => void>(() => undefined)
  // the step the next-move card shows, for the route answer it belongs to (a new answer starts at step 1)
  const [moveAt, setMoveAt] = useState({ key: -1, index: 0 })
  // walking the route with the camera (CameraWalk); `muted` stops it reading each step aloud
  const [walking, setWalking] = useState(false)
  const [muted, setMuted] = useState(false)
  // live tracking along the route (useTracking): counted steps between fixes
  const [tracking, setTracking] = useState(false)
  const cameraVideo = useRef<HTMLVideoElement>(null)
  const [fitKey, setFitKey] = useState(0)
  const [look, setLook] = useState<ViewMode>('3d') // tilted, or flat once the user tilts straight down
  // what the camera frames (an answer's rooms, items or route part), and the "you are here" figure
  const [focus, setFocus] = useState<Focus | null>(null)
  const focusKey = useRef(0)
  const frameOn = (points: [number, number, number][], span: number, heading?: [number, number]) => setFocus({ key: ++focusKey.current, points, span, heading })
  const [me, setMe] = useState<Me | null>(null)
  // the route answer whose step-by-step guide was started (Start, or "start"); a new answer ends it
  const [guideKey, setGuideKey] = useState(-1)
  // the step the Guide just moved the card to: its reply already covers it, so it isn't read out again
  const quietStep = useRef<number | null>(null)

  useEffect(() => sessionStorage.removeItem(noteKey(buildingId)), [buildingId])

  // ---- dev tool (DEV_TOOLS only): the panel, plan display settings, and the answer drawn on the plan
  const [settings, setSettings] = useState(DEFAULT_SETTINGS)
  const [story, setStory] = useState<Story>(EMPTY_STORY)
  const storyRef = useRef(story)
  const [devOpen, setDevOpen] = useState(() => DEV_TOOLS && readFlag(DEV_KEY, false))
  const [log, setLog] = useState<LogEntry[]>([])
  useEffect(() => writeFlag(DEV_KEY, devOpen), [devOpen])
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const typing = event.target instanceof HTMLElement && event.target.closest('input, textarea, select')
      if (DEV_TOOLS && event.key === '`' && !typing) setDevOpen((open) => !open)
    }
    addEventListener('keydown', onKey)
    return () => removeEventListener('keydown', onKey)
  }, [])
  const reloadPlan = useCallback(() => {
    if (sessionId) void api.plan(sessionId).then(setPlan).catch((reason) => setError(String(reason)))
  }, [sessionId])
  // another viewer (signed in or out): the backend re-filters the session on this request, the plan follows
  const viewerVersion = useRef(access.version)
  useEffect(() => {
    if (viewerVersion.current === access.version) return
    viewerVersion.current = access.version
    if (!sessionId) return
    api.plan(sessionId).then(setPlan).catch((reason) => {
      // a building that isn't public, once signed out: no longer there for this viewer
      if (reason instanceof ApiError && reason.status === 404) {
        notify('This building is not open to you.')
        onBack()
      } else setError(String(reason))
    })
  }, [access.version, sessionId, onBack])

  // access mode: the remembered preferences for this building go to the session when it opens, when the viewer
  // changes and after every edit (src/access/preferences.ts); remembering off sends none
  const sessionValues = useMemo(() => JSON.stringify(effective(preferences, buildingId)), [preferences, buildingId])
  const autoCapture = preferences.remember && preferences.auto_capture
  useEffect(() => {
    if (!access.mode || !sessionId) return
    const timer = setTimeout(() => {
      api.sessionPreferences(sessionId, JSON.parse(sessionValues), autoCapture).catch(() => undefined)
    }, 150)
    return () => clearTimeout(timer)
  }, [access.mode, sessionId, sessionValues, autoCapture, access.version])

  // access mode: the building's moving objects, polled about once a second while this screen is open (slower
  // after errors)
  const hasPlan = plan !== null
  useEffect(() => {
    if (!access.mode || !hasPlan) return
    let stopped = false
    let timer: ReturnType<typeof setTimeout> | undefined
    let wait = OBJECTS_POLL_MS
    const poll = () => {
      clearTimeout(timer)
      api
        .objects(buildingId)
        .then((items) => {
          if (stopped) return
          setObjects(items)
          wait = OBJECTS_POLL_MS
        })
        .catch(() => (wait = Math.min(wait * 2, OBJECTS_POLL_MAX_MS)))
        .finally(() => {
          if (!stopped) timer = setTimeout(poll, wait)
        })
    }
    pollNow.current = poll
    poll()
    return () => {
      stopped = true
      clearTimeout(timer)
      pollNow.current = () => undefined
    }
  }, [access.mode, hasPlan, buildingId, access.version])
  /** Show a new answer and take the camera to it: a route whole (every floor stacked when it crosses floors), or
   * the rooms and items found (their floor, zoomed to them). */
  const present = (next: Story) => {
    const changed = next.key !== storyRef.current.key
    storyRef.current = next
    setStory(next)
    if (!plan || !changed) return
    if (next.route) {
      const runs = routeRuns(next.route.line)
      if (!runs.length) return
      const points = next.route.line.map(([x, y, at]) => [x, y, at] as [number, number, number])
      const outdoor = next.route.next && origin ? outdoorWalk(next.route.next, origin, runs[runs.length - 1].floor) : null
      if (outdoor) points.push([...outdoor.to, outdoor.floor])
      const floorsCrossed = new Set(runs.map((run) => run.floor))
      setFloor(runs[0].floor)
      setStacked(floorsCrossed.size > 1)
      frameOn(points, FOCUS_ROUTE_M)
      return
    }
    const rooms = plan.spaces.filter((space) => next.focus.includes(space.id))
    const items = plan.assets.filter((asset) => next.assets.includes(asset.id))
    const points: [number, number, number][] = [
      ...rooms.flatMap((space) => space.polygon.map(([x, y]) => [x, y, space.floor] as [number, number, number])),
      ...items.map((asset) => [...asset.position, asset.floor] as [number, number, number]),
    ]
    if (!points.length) return
    const floorsHit = new Set(points.map(([, , at]) => at))
    // the floor with most of the answer on it, unless it spreads over several: then all floors, stacked
    const target = rooms[0]?.floor ?? items[0]?.floor
    setFloor(target)
    setStacked(floorsHit.size > 1)
    frameOn(points, FOCUS_ROOM_M)
  }
  const onEvents = (events: DevEvent[], spoken = false) => {
    if (events.some((event) => event.type === 'change')) reloadPlan()
    // the Guide switched to the Edit mode: the Builder takes the request once the draft is open
    const edit = events.find((event) => event.type === 'edit_mode')
    if (edit?.type === 'edit_mode') {
      if (access.mode && !access.admin) {
        setMessages((list) => [...list, { role: 'note', text: 'Editing this building needs its admin account.' }])
      } else {
        handOver.current = edit.request ? { text: edit.request, spoken } : null
        setEditing(true)
      }
    }
    // access mode: what the Guide heard you prefer, remembered when you let it
    for (const event of events) {
      if (event.type === 'preference' && access.mode) capture(event.scope, event.values, buildingId, (id) => plan?.spaces.find((space) => space.id === id)?.name)
    }
    // the user told the Guide where they are: the figure stands there, and the map goes to it (a route in the same
    // answer is framed instead, below)
    const located = events.find((event) => event.type === 'location')
    const room = located?.type === 'location' ? plan?.spaces.find((space) => space.id === located.space_id) : undefined
    if (room) {
      setMe({ at: room.label, floor: room.floor, space: room.id, label: room.name }) // the session knows it already
      setFloor(room.floor)
      setStacked(false)
      frameOn(room.polygon.map(([x, y]) => [x, y, room.floor] as [number, number, number]), FOCUS_ROOM_M)
    }
    // while tracking, the Guide placing you in a room of the route (e.g. "Where am I?" from the camera) is a fix,
    // not a new answer: the route stays and you are where it enters that room
    const route = storyRef.current.route
    const placed = tracking && route ? events.find((event) => event.type === 'highlight' && !event.style && event.space_ids.length === 1 && !event.asset_ids?.length) : undefined
    if (placed?.type === 'highlight' && route) {
      const entered = route.steps.findIndex((step) => step.kind !== 'connector' && placed.space_ids.includes(step.to_id))
      if (entered >= 0) {
        fixAtStep(Math.min(entered + 1, route.steps.length - 1), 'camera')
        return
      }
    }
    present(applyEvents(storyRef.current, events))
    // the Guide talked about another step of the route being followed: the step card (and the map) go there,
    // without reading the step out again over the reply (a new route in the same answer starts at step 1)
    const moved = events.findLast((event) => event.type === 'route_step')
    if (moved?.type === 'route_step' && route && !events.some((event) => event.type === 'route')) {
      const index = Math.max(0, Math.min(route.steps.length - 1, moved.index))
      quietStep.current = index
      setGuideKey(storyRef.current.key)
      onMove(index)
    }
  }

  useEffect(() => {
    let cancelled = false
    // fetched since the tap (./opening.ts); shown once the map's fly-in has landed, so the model takes over from it
    const opening = take(buildingId)
    Promise.all([opening.promise, settled()])
      .then(([{ sessionId: id, plan: next }]) => {
        if (cancelled) return
        setSessionId(id)
        setPlan(next)
        const ground = next.floors.findIndex((item) => item.level === 0)
        setFloor(ground >= 0 ? ground : 0)
        setStacked(next.floors.length > 1) // first look: the whole building, every floor stacked
      })
      .catch((reason) => !cancelled && setError(String(reason)))
    return () => {
      cancelled = true
      opening.release()
    }
  }, [buildingId])

  // "Opening the building…" only once the wait is noticeable: over the map the fly-in is the wait (a timer, not a CSS
  // delay: the app's reduced-motion rule switches CSS animations off)
  const [slow, setSlow] = useState(false)
  useEffect(() => {
    const timer = setTimeout(() => setSlow(true), origin ? 2400 : 900)
    return () => clearTimeout(timer)
  }, [origin])

  // the map's own block of this building gives way to the model while this screen is up
  useEffect(() => {
    if (!origin || !plan) return
    const ground = plan.floors.find((item) => item.level === 0)?.elevation_m ?? plan.floors[0]?.elevation_m ?? 0
    const height = Math.max(3, ...plan.floors.map((item) => item.elevation_m + item.height_m - ground))
    hideBlocks(buildingId, origin, (plan.outlines ?? []).flatMap((floor) => floor.map((polygon) => polygon[0] ?? [])), height)
  }, [buildingId, origin, plan])
  useEffect(() => () => showBlocks(buildingId), [buildingId])
  // ...and the model draws them as a wireframe instead
  const [shell, setShell] = useState<ShellBlock[]>([])
  useEffect(() => onShell(setShell), [])

  // the map under the model: where the model's camera starts, and the camera the map follows
  const alone = !origin || showing === 'alone'
  const mapCamera = useMemo(
    () => (origin ? { intro: () => mapView(origin), follow: leaving ? undefined : (view: Parameters<typeof follow>[1]) => follow(origin, view) } : undefined),
    [origin, leaving],
  )

  const routeSteps = useMemo(() => story.route?.steps ?? [], [story.route])
  const moving = routeSteps.length > 0
  const moveIndex = moveAt.key === story.key ? Math.min(moveAt.index, routeSteps.length - 1) : 0
  const guiding = moving && guideKey === story.key
  const track = useMemo(() => (story.route ? routeTrack(story.route.line, story.route.legs) : null), [story.route])
  const onMove = (index: number) => {
    setMoveAt({ key: story.key, index })
    // walking steps happen on their room's floor; a stairs or lift step changes it on the step after
    const step = routeSteps[index]
    const at = step && step.kind !== 'connector' && plan ? plan.floors.findIndex((item) => item.name === step.floor) : -1
    if (at >= 0 && (at !== floor || stacked)) {
      setFloor(at)
      setStacked(false)
    }
    // the camera follows the step: the stretch of the route it covers (a ride: where it starts)
    if (track && step) {
      const from = track.starts[index] ?? 0
      const to = track.starts[index + 1] ?? from
      const points = Array.from({ length: 9 }, (_, i) => track.at(from + ((to - from) * i) / 8)).map(({ at: [x, y], floor: on }) => [x, y, on] as [number, number, number])
      const here = at >= 0 ? at : points[0][2]
      if (at < 0 && (here !== floor || stacked)) {
        setFloor(here)
        setStacked(false)
      }
      // and turns to face the way the step goes, like a sat-nav (a ride keeps the current turn)
      frameOn(points.filter(([, , on]) => on === here), FOCUS_STEP_M, to - from > 0.5 ? headingAt(track, from, to) : undefined)
    }
  }
  /** Start the step-by-step guide: step 1, read aloud, then each next one when the user says they are there. */
  const startGuide = () => {
    setGuideKey(story.key)
    onMove(0)
  }
  // the walk outside to a nearby building, drawn from the exit to its entrance
  const outdoor = useMemo((): Outdoor | null => {
    const next = story.route?.next
    if (!next || !origin || !story.route) return null
    const runs = routeRuns(story.route.line)
    return runs.length ? outdoorWalk(next, origin, runs[runs.length - 1].floor) : null
  }, [story.route, origin])
  const continueTo = (next: NextBuilding) => {
    const arrival: Arrival = { entrance: next.entrance, destination: next.destination, from: sessionId, fromName: plan?.building.name ?? '', name: next.name, destinationName: next.destination_name }
    sessionStorage.setItem(arrivalKey(next.building), JSON.stringify(arrival))
    voice.stop()
    onOpen(next.building)
  }
  const kinds = useMemo(() => routeSteps.map((step) => step.kind), [routeSteps])
  const { position, fixAtStep } = useTracking({ track, routeKey: story.key, active: tracking && moving, step: moveIndex, kinds, onStep: onMove })
  const followed = tracking && moving && !!position && !!track
  const shownStory = useMemo(() => {
    const placed = outdoor ? { ...story, outdoor } : story
    // the step being followed, on the route band: walked part, this step, where it ends; and you at its start
    // (or where tracking puts you)
    const stepping = moving && (guiding || walking || moveIndex > 0)
    const from = track?.starts[moveIndex] ?? 0
    const to = track?.starts[moveIndex + 1] ?? from
    const end = track?.at(to)
    const step = stepping && track && end
      ? { done: track.toLine(position ? position.metres : from), from: track.toLine(from), to: track.toLine(to), end: end.at, floor: end.floor, next: routeSteps[moveIndex + 1] ?? null }
      : undefined
    const you = position && track
      ? { ...track.at(position.metres), stale: position.stale }
      : stepping && track && to - from > 0.5 ? { ...track.at(from + 0.01), stale: false } : undefined
    return { ...placed, step, you }
  }, [story, position, track, outdoor, moving, guiding, walking, moveIndex, routeSteps])

  // the "you are here" figure: the Guide learns the room (and stops asking where the user is), and where in it the
  // figure stands (the next route's line starts there)
  const placeMe = (next: Me | null) => {
    setMe(next)
    const point = next ? next.door ?? next.at : null // outside, the route starts at the entrance
    const before = me ? me.door ?? me.at : null
    const moved = (next?.space ?? null) !== (me?.space ?? null) || point?.[0] !== before?.[0] || point?.[1] !== before?.[1]
    if (sessionId && moved) void api.setLocation(sessionId, next?.space ?? null, point).catch(() => undefined)
  }

  // arriving from a nearby building: placed at the entrance, the route on drawn, one line in the chat
  const arrived = useRef(false)
  useEffect(() => {
    if (!sessionId || !plan || arrived.current) return
    arrived.current = true
    let arrival: Arrival | null = null
    try {
      arrival = JSON.parse(sessionStorage.getItem(arrivalKey(buildingId)) ?? 'null') as Arrival | null
    } catch {
      arrival = null
    }
    sessionStorage.removeItem(arrivalKey(buildingId))
    if (!arrival) return
    const door = plan.openings.find((opening) => opening.id === arrival.entrance)
    void api
      .arrive(sessionId, arrival.entrance, arrival.destination, arrival.from)
      .then((reply) => {
        const room = plan.spaces.find((space) => space.id === reply.location.space_id)
        if (door && room) setMe({ at: door.position, floor: door.floor, space: room.id, label: room.name })
        setMessages((list) => [
          ...list,
          { role: 'note', text: reply.route.reachable ? `Welcome to ${arrival.name}, coming over from ${arrival.fromName}. The way on to ${arrival.destinationName} is on the map — press Start when you're in.` : `Welcome to ${arrival.name}. I could not find a way on to ${arrival.destinationName}: ${reply.route.reason ?? 'no route'}.` },
        ])
        onEvents(reply.events)
      })
      .catch((reason) => setMessages((list) => [...list, { role: 'note', text: `Could not continue the route here: ${String(reason)}` }]))
    // onEvents reads refs and the plan; run once per opened building
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, plan, buildingId])

  const insets: Insets = wide
    ? { top: TOP_PX + 8 + (moving ? MOVE_PX + (followed ? TRACK_PX : 0) : 0), right: 24, bottom: 24, left: 16 + PANEL_PX + 24 + (devOpen ? DEV_PX : 0) }
    : editing
      ? { top: TOP_PX + 8 + EDIT_BAR_PX, right: 0, bottom: EDIT_PX, left: 0 }
      : { top: TOP_PX + 8 + (moving ? MOVE_PX + (followed ? TRACK_PX : 0) : 0), right: 0, bottom: GUIDE_PX, left: 0 }

  // the whole building is centred on the screen: on a wide screen the Guide is a card in the bottom-left corner,
  // not a column, so it does not push the building right (the floor rail on the right is mirrored on the left);
  // an answer's own rooms still keep clear of the card (`insets`)
  const frameInsets: Insets = wide ? { ...insets, left: devOpen ? DEV_PX + 16 : RAIL_PX, right: RAIL_PX } : insets

  const current = plan?.floors[floor]
  const rooms = plan ? plan.spaces.filter((space) => space.floor === floor && space.type === 'room').length : 0
  const suggestions = useMemo(() => (plan ? suggest(plan, plan.floors[floor]?.name ?? '') : []), [plan, floor])

  const info = useMemo((): InfoCard | null => {
    if (!plan || !selected) return null
    if (selected.kind === 'space') {
      const space = plan.spaces.find((item) => item.id === selected.id)
      if (!space) return null
      const kind = CATEGORY_LABEL[space.room_type] ?? 'Room'
      return { title: space.name, meta: `${kind} · ${plan.floors[space.floor].name} · ${Math.round(space.area_m2)} m²`, directions: `How do I get to ${space.name}?` }
    }
    const asset = plan.assets.find((item) => item.id === selected.id)
    if (!asset) return null
    const room = plan.spaces.find((item) => item.id === asset.space)
    return {
      title: asset.name,
      meta: `${humanise(asset.type)} · ${room?.name ?? 'Unknown room'} · ${plan.floors[asset.floor].name}`,
      detail: `${asset.size[0].toFixed(1)} × ${asset.size[1].toFixed(1)} m`,
      directions: `How do I get to ${asset.name}?`,
    }
  }, [plan, selected])

  /** Short commands about the route on the map, handled here instead of by the Guide: "start", then "I'm there" /
   * "next", "back", "repeat". True when handled. */
  const routeCommand = (text: string): boolean => {
    const words = text.trim().split(/\s+/).length
    if (!moving) return false
    if (!guiding && (START.test(text) && words <= 3 || START_SAID.test(text) && words <= 6)) return startGuide(), true
    if (!guiding || words > 3) return false
    const step = (to: number) => onMove(Math.max(0, Math.min(routeSteps.length - 1, to)))
    if (NEXT.test(text)) {
      if (moveIndex >= routeSteps.length - 1) speak(story.route?.next ? `You're at the exit. Tap Continue for ${story.route.next.name}.` : 'You have arrived.')
      else step(moveIndex + 1)
      return true
    }
    if (BACK.test(text)) return step(moveIndex - 1), true
    if (REPEAT.test(text)) {
      const again = routeSteps[moveIndex]?.text
      if (again) setTimeout(() => speak(again, { conversation: true }), 0)
      return true
    }
    return false
  }

  /** `via`: how the question came. 'voice' (heard) is answered aloud and the conversation goes on; 'tap' (a
   * button or chip) is answered aloud once; 'text' (typed) is answered in text — aloud too while walking, unmuted. */
  const send = async (text: string, via: 'voice' | 'tap' | 'text' = 'text', photo?: string) => {
    if (!sessionId) return
    const spoken = via === 'voice'
    const aloud = spoken || (walking ? !muted : via === 'tap')
    const picked = selected?.id
    setSelected(null)
    setMessages((list) => [...list, { role: 'user', text, spoken }, { role: 'guide', text: '', live: true }])
    setPending(true)
    let key = 0
    const onLive = (update: (steps: Step[]) => Step[]) =>
      setMessages((list) => list.map((item) => (item.role === 'guide' && item.live ? { ...item, steps: update(item.steps ?? []) } : item)))
    // an answer read aloud is spoken while the Guide still writes: its `say` sentences go straight to the voice
    const live: { speech?: Speech } = {}
    // a tapped question whose answer asks something back ("Where are you now?") listens for the answer
    let asked = false
    const talk = { conversation: spoken, listenAfter: () => asked }
    try {
      const turn = await api.chatStream(sessionId, text, {
        channel: aloud ? 'voice' : 'text',
        heard: spoken,
        selected: picked,
        photo,
        // only once the user follows it (Start, camera walk, or moved the card): a route just drawn isn't walked yet
        routeStep: moving && (guiding || walking || moveIndex > 0) ? moveIndex : undefined,
        onStep: (step) => onLive((steps) => addStep(steps, step, key++)),
        onSay: (sentence) => (live.speech ??= voice.stream(talk)).add(sentence),
      })
      setMessages((list) =>
        list.map((item) =>
          item.role === 'guide' && item.live
            ? { role: 'guide', text: turn.reply, spoken, steps: settle(item.steps ?? []), route: turn.events.some((event) => event.type === 'route') }
            : item,
        ),
      )
      onEvents(turn.events, spoken)
      asked = via === 'tap' && turn.reply.includes('?')
      if (live.speech) live.speech.end()
      else if (aloud && !queued.current) voice.speak(turn.spoken ?? turn.reply, talk)
    } catch (reason) {
      live.speech?.end() // let what was already said finish
      // a server failure (e.g. the API credit ran out) comes as a readable sentence; anything else as a short note
      const readable = reason instanceof ServiceError
      const text = readable ? reason.message : `The Guide could not answer: ${reason instanceof Error ? reason.message : String(reason)}`
      setMessages((list) => [...list.filter((item) => !(item.role === 'guide' && item.live)), { role: 'note', text }])
      if (aloud && readable) voice.speak(text) // asked by voice: told by voice, once
      else voice.idle()
    } finally {
      setPending(false)
    }
  }

  const voice = useVoice({
    onUtterance: (text) => {
      // in the Edit mode the voice talks to the Builder
      if (editing) {
        if (draft.asking || !draft.state) return false
        void draft.ask(text, { spoken: true, speak: (reply) => voice.speak(reply, { conversation: true }), idle: () => voice.idle() })
        return true
      }
      if (!sessionId) return false
      // talked over an answer that is still being written: asked as soon as that one is done
      if (pending) return (queued.current = text), true
      if (!walking && routeCommand(text)) return false
      if (walking && moving) {
        const words = text.trim().split(/\s+/).length
        const step = (to: number) => onMove(Math.max(0, Math.min(routeSteps.length - 1, to)))
        if (words <= 3 && NEXT.test(text)) return step(moveIndex + 1), false
        if (words <= 3 && BACK.test(text)) return step(moveIndex - 1), false
        if (words <= 3 && REPEAT.test(text)) {
          const again = routeSteps[moveIndex]?.text
          if (again) setTimeout(() => voice.speak(again), 0) // after the voice loop has settled back to idle
          return false
        }
        void send(text, 'voice', grabFrame(cameraVideo.current))
        return true
      }
      void send(text, 'voice')
      return true
    },
  })
  const queued = useRef<string | null>(null)
  useEffect(() => {
    const text = queued.current
    if (pending || !text) return
    queued.current = null
    void send(text, 'voice')
    // send is recreated every render; the queued question goes once the turn before it is done
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pending])
  // A spoken question starts a conversation: after the reply the Guide listens again by itself (and the user can
  // talk over the reply); silence or a tap ends it. Typed questions and walk-mode steps don't (voice/useVoice.ts).
  // Scribe listens for this conversation's building names (keyterms, voice/scribe.ts).
  useEffect(() => setScribeSession(sessionId), [sessionId])

  // walking with the camera, or the step-by-step guide: each step is read aloud when it comes up (not on mute); the
  // guide then listens for "I'm there" when the conversation is hands-free
  const { speak } = voice
  const stepText = (walking || guiding) && !muted ? routeSteps[moveIndex]?.text : undefined
  useEffect(() => {
    const quiet = quietStep.current === moveIndex
    quietStep.current = null
    if (stepText && !quiet) speak(`Step ${moveIndex + 1}. ${stepText}`, { conversation: guiding && !walking, waitMs: STEP_WAIT_MS })
    // guiding/walking only decide how; a new step text is what triggers it
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stepText, moveIndex, speak])

  const pickFloor = (index: number | 'all') => {
    setStacked(index === 'all')
    if (index !== 'all') setFloor(index)
    setSelected(null)
    setPopover(null)
  }

  const ThemeIcon = THEME_ICON[theme.mode]

  // while editing the model is the draft's (the original until the draft's plan has loaded), one floor at a time
  const shownPlan = editing && draft.plan ? draft.plan : plan
  const editFloorId = shownPlan?.floors[floor]?.id
  const focusIssue = (issue: Issue) => {
    const building = draft.state?.building
    const id = issue.ids[0]
    const space = building?.spaces.find((item) => item.id === id)
    const opening = building?.openings.find((item) => item.id === id)
    const asset = building?.assets.find((item) => item.id === id)
    const target = space ?? opening ?? asset
    const index = target && shownPlan ? shownPlan.floors.findIndex((item) => item.id === target.floor_id) : -1
    if (!target || index < 0) return
    setFloor(index)
    draft.setTool('select')
    draft.setSelected({ kind: space ? 'space' : opening ? 'opening' : 'asset', id })
  }
  useEffect(() => {
    const request = handOver.current
    if (!editing || !request || !draft.state || draft.asking) return
    handOver.current = null
    void draft.ask(request.text, request.spoken
      ? { spoken: true, speak: (reply) => voice.speak(reply, { conversation: true }), idle: () => voice.idle() }
      : {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editing, draft.state, draft.asking])
  // a Builder proposal on another floor: go there, so its ghost is in view
  useEffect(() => {
    const index = draft.proposalFloorId && shownPlan ? shownPlan.floors.findIndex((item) => item.id === draft.proposalFloorId) : -1
    if (index < 0) return
    setFloor(index)
    setStacked(false) // the ghost is drawn on one floor
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft.proposalFloorId])
  const saveDraft = async (name: string) => {
    const saved = await draft.save(name)
    if (!saved) return
    sessionStorage.setItem(noteKey(saved), `Saved “${name}” from the Edit mode — this is the edited building.`)
    setEditing(false)
    onOpen(saved)
  }

  return (
    <main className={`screen${devOpen && wide ? ' dev-open' : ''}${origin ? ' on-map' : ''}${alone ? ' alone' : ''}${plan ? ' ready' : ''}${leaving ? ' leaving' : ''}`}>
      <div className="screen-stage" aria-hidden="true" />
      {shownPlan && (
        <PlanView
          plan={shownPlan}
          floor={floor}
          stacked={stacked}
          palette={palette}
          selected={editing ? (draft.selected && draft.selected.kind !== 'opening' ? { kind: draft.selected.kind, id: draft.selected.id } : null) : selected}
          insets={insets}
          frameInsets={frameInsets}
          fitKey={fitKey}
          onSelect={editing ? draft.setSelected : setSelected}
          onPickFloor={(index) => {
            setFloor(index)
            setStacked(false)
          }}
          onTilt={setLook}
          spread={look === '3d'}
          settings={settings}
          story={editing ? EMPTY_STORY : shownStory}
          objects={access.mode && !editing ? objects : undefined}
          focus={editing ? null : focus}
          me={editing ? null : me}
          onMe={editing ? undefined : placeMe}
          onNext={story.route?.next && !editing ? () => continueTo(story.route!.next!) : undefined}
          align={editing && !stacked ? align : undefined}
          // the Door / Item tools place where you tap — on the floor you are on, or (all floors) on the one tapped,
          // which the view then steps onto
          onTap={editing && draft.tool !== 'select' ? (tap) => {
            const floorId = shownPlan?.floors[tap.floor]?.id
            if (floorId) draft.placeAt(floorId, tap.at, tap.pixelsPerMetre)
            return true
          } : undefined}
          ground={alone}
          city={alone ? undefined : { shell, ground: groundColour(theme.dark) }}
          camera={mapCamera}
          onMiss={editing || alone ? undefined : (x, y) => {
            const id = pinAt(x, y)
            if (id && id !== buildingId) onOpen(id)
            return Boolean(id)
          }}
        />
      )}
      {editing && !stacked && draft.state && editFloorId && (
        <EditLayer
          building={draft.state.building}
          floorId={editFloorId}
          issues={draft.state.issues}
          selected={draft.selected}
          onSelect={draft.setSelected}
          onOps={draft.onOps}
          busy={draft.busy}
          revision={draft.revision}
          ghost={draft.proposal?.building ?? null}
          tool={draft.tool}
          preset={draft.preset}
          align={align}
        />
      )}

      {!plan && (slow || error) && (
        <div className="screen-status" role="status">
          {error ? <p>Could not open this building. {error}</p> : <p>Opening the building…</p>}
        </div>
      )}

      <header className="hud-top">
        <button type="button" className="hud-btn" onClick={onBack} aria-label="All buildings">
          <ChevronLeft size={19} strokeWidth={2.2} />
        </button>
        <div className="hud-place">
          <h1>{plan?.building.name ?? 'Building'}</h1>
          {plan && (
            <p>
              {editing ? `Editing a copy${draft.state?.draft.steps ? ` · ${draft.state.draft.steps} ${draft.state.draft.steps === 1 ? 'change' : 'changes'}` : ''}` : stacked ? 'All floors' : `${rooms} ${rooms === 1 ? 'room' : 'rooms'}`}
            </p>
          )}
        </div>
        {plan && plan.floors.length > 1 && (
          <button
            type="button"
            className="hud-chip floor-chip"
            aria-haspopup="menu"
            aria-expanded={popover === 'floors'}
            aria-label={`Floor: ${stacked ? 'all floors' : current?.name}`}
            onClick={() => setPopover((open) => (open === 'floors' ? null : 'floors'))}
          >
            {stacked ? <Layers size={16} strokeWidth={2} /> : floorTab(current?.level ?? 0)}
            <ChevronsUpDown size={14} strokeWidth={2} />
          </button>
        )}
        {plan && (
          <button
            type="button"
            className="hud-btn"
            aria-haspopup="menu"
            aria-expanded={popover === 'menu'}
            aria-label="More"
            onClick={() => setPopover((open) => (open === 'menu' ? null : 'menu'))}
          >
            <Ellipsis size={19} strokeWidth={2} />
          </button>
        )}
      </header>

      {!editing && !moving && story.elsewhere && story.elsewhere.length > 0 && (
        <Elsewhere
          buildings={story.elsewhere}
          onDirections={(item) => void send(`Take me to ${item.first ?? 'it'} in ${item.name}.`, 'tap')}
          onOpen={(item) => onOpen(item.building)}
          onClose={() => present({ ...EMPTY_STORY, key: storyRef.current.key + 1 })}
        />
      )}

      {!editing && moving && !walking && (
        <NextMove
          steps={routeSteps}
          index={moveIndex}
          lengthM={story.route?.length_m ?? null}
          profile={story.route?.profile ?? null}
          onIndex={onMove}
          guiding={guiding}
          onStart={startGuide}
          next={story.route?.next ?? null}
          onContinue={(next) => continueTo(next)}
          onClose={() => {
            setTracking(false)
            present({ ...EMPTY_STORY, key: storyRef.current.key + 1 })
          }}
          onCamera={() => setWalking(true)}
          tracking={tracking}
          position={followed ? position : null}
          track={followed ? track : null}
          onTrack={async () => {
            if (!tracking) await askForMotion() // iOS asks from this tap; a refusal leaves door and camera fixes
            setTracking((on) => !on)
          }}
        />
      )}

      {plan && popover && <div className="hud-scrim" onClick={() => setPopover(null)} />}
      {/* on a phone the floors open from the chip; on a wide screen they stay open on the right */}
      {plan && plan.floors.length > 1 && (
        <nav className={`hud-pop floors${popover === 'floors' ? ' open' : ''}`} aria-label="Floors" role="menu">
          <button type="button" role="menuitemradio" aria-checked={stacked} onClick={() => pickFloor('all')} title="All floors">
            <span className="tab"><Layers size={15} strokeWidth={2} /></span>
            <span className="name">All floors</span>
          </button>
          {[...plan.floors.keys()].reverse().map((index) => (
            <button key={index} type="button" role="menuitemradio" aria-checked={!stacked && index === floor} onClick={() => pickFloor(index)} title={plan.floors[index].name}>
              <span className="tab">{floorTab(plan.floors[index].level)}</span>
              <span className="name">{plan.floors[index].name}</span>
            </button>
          ))}
        </nav>
      )}
      {plan && popover === 'menu' && (
        <div className="hud-pop menu" role="menu">
          <button type="button" role="menuitem" onClick={() => { setEditing((on) => !on); setPopover(null) }} title="Edit this building (on a copy)">
            <PencilRuler size={17} strokeWidth={2} />
            {editing ? 'Stop editing' : 'Edit this building'}
            {editing && <Check size={16} className="on" />}
          </button>
          <button type="button" role="menuitem" onClick={() => { setFitKey((key) => key + 1); setPopover(null) }}>
            <Scan size={17} strokeWidth={2} />
            Show it all
          </button>
          {origin && (
            <button type="button" role="menuitem" onClick={() => { onShowing(showing === 'city' ? 'alone' : 'city'); setPopover(null) }}>
              {showing === 'city' ? <Box size={17} strokeWidth={2} /> : <MapIcon size={17} strokeWidth={2} />}
              {showing === 'city' ? 'Show the building alone' : 'Show it in the city'}
            </button>
          )}
          <button type="button" role="menuitem" onClick={theme.cycle}>
            <ThemeIcon size={17} strokeWidth={2} />
            {THEME_LABEL[theme.mode]}
          </button>
          {access.mode && (
            <>
              <button type="button" role="menuitem" onClick={() => { openPanel('preferences'); setPopover(null) }}>
                <SlidersHorizontal size={17} strokeWidth={2} />
                Preferences
              </button>
              <button type="button" role="menuitem" onClick={() => { setSettingsOpen(true); setPopover(null) }}>
                <Settings2 size={17} strokeWidth={2} />
                Building settings
              </button>
            </>
          )}
          {access.mode && !access.email && (
            <button type="button" role="menuitem" onClick={() => { openPanel('signin'); setPopover(null) }}>
              <LogIn size={17} strokeWidth={2} />
              Sign in
            </button>
          )}
          {access.mode && access.email && (
            <>
              <p className="account" title={access.email}>{access.email}</p>
              {access.needsPassword && (
                <button type="button" role="menuitem" onClick={() => { openPanel('password'); setPopover(null) }}>
                  <KeyRound size={17} strokeWidth={2} />
                  Set a password
                </button>
              )}
              <button type="button" role="menuitem" onClick={() => { void signOut(); setPopover(null) }}>
                <LogOut size={17} strokeWidth={2} />
                Sign out
              </button>
            </>
          )}
          {DEV_TOOLS && (
            <button type="button" role="menuitem" onClick={() => { setDevOpen((open) => !open); setPopover(null) }}>
              <Wrench size={17} strokeWidth={2} />
              Dev tools
              {devOpen && <Check size={16} className="on" />}
            </button>
          )}
        </div>
      )}

      {access.mode && settingsOpen && (
        <BuildingSettings
          buildingId={buildingId}
          plan={plan}
          admin={access.admin}
          objects={objects}
          onClose={() => setSettingsOpen(false)}
          onSaved={reloadPlan}
          onObjects={() => pollNow.current()}
        />
      )}

      {plan && sessionId && devOpen && (
        <DevPanel
          sessionId={sessionId}
          plan={plan}
          story={story}
          selected={selected}
          settings={settings}
          onSettings={setSettings}
          onEvents={onEvents}
          onStory={(make) => present(make(storyRef.current))}
          onReset={async () => {
            await devApi.reset(sessionId)
            present({ ...EMPTY_STORY, key: storyRef.current.key + 1 })
            reloadPlan()
          }}
          onClose={() => setDevOpen(false)}
          log={log}
          onLog={(entry) => setLog((list) => [...list.slice(-199), entry])}
          themeLabel={THEME_LABEL[theme.mode]}
          onTheme={theme.cycle}
        />
      )}

      {editing && (
        <EditBar draft={draft} onFocusIssue={focusIssue} onDone={() => setEditing(false)} onSave={(name) => void saveDraft(name)} />
      )}

      {/* one assistant card: the Guide, or while editing the Builder (with the selection's inspector in it) */}
      {editing ? (
        <Guide
          messages={draft.messages}
          pending={draft.asking}
          voice={{ ...voice, supported: voiceSupported() }}
          info={null}
          suggestions={draft.suggestions}
          route={false}
          onSend={(text, tapped) => void draft.ask(text, tapped ? { speak: (reply) => voice.speak(reply), idle: () => voice.idle() } : {})}
          onCloseInfo={() => draft.setSelected(null)}
          onClear={() => {
            voice.stop()
            draft.setMessages([])
          }}
          persona={BUILDER}
          card={draft.proposal || draft.selected || draft.tool !== 'select' ? <EditCard draft={draft} /> : undefined}
        />
      ) : (
        <Guide
          messages={messages}
          pending={pending}
          voice={{ ...voice, supported: voiceSupported() }}
          info={info}
          suggestions={suggestions}
          route={moving}
          onSend={(text, tapped) => {
            if (routeCommand(text)) setMessages((list) => [...list, { role: 'user', text }])
            else void send(text, tapped ? 'tap' : 'text')
          }}
          onCloseInfo={() => setSelected(null)}
          onClear={() => {
            voice.stop()
            setMessages([])
          }}
        />
      )}

      {walking && moving && (
        <CameraWalk
          steps={routeSteps}
          index={moveIndex}
          lengthM={story.route?.length_m ?? null}
          profile={story.route?.profile ?? null}
          voice={{ ...voice, supported: voiceSupported() }}
          answer={messages.at(-1)}
          pending={pending}
          muted={muted}
          video={cameraVideo}
          onIndex={onMove}
          position={followed ? position : null}
          track={followed ? track : null}
          onMute={() => {
            setMuted((on) => !on)
            voice.stop()
          }}
          onWhereAmI={(photo) => void send(WHERE_AM_I, 'tap', photo)}
          onClose={() => {
            setWalking(false)
            voice.stop()
          }}
        />
      )}
    </main>
  )
}

/** The dev panel (src/dev/) is for building and testing: on in the Vite dev server, else only with ?dev in the URL. */
const DEV_TOOLS = import.meta.env.DEV || new URLSearchParams(location.search).has('dev')
const DEV_PX = 372
const DEV_KEY = 'ttyb-dev-open'
const OBJECTS_POLL_MS = 1000
const OBJECTS_POLL_MAX_MS = 15_000
function readFlag(key: string, fallback: boolean) {
  try {
    const value = localStorage.getItem(key)
    return value === null ? fallback : value === 'true'
  } catch {
    return fallback
  }
}
function writeFlag(key: string, value: boolean) {
  try {
    localStorage.setItem(key, String(value))
  } catch {
    // storage unavailable: the choice just isn't remembered
  }
}

/** The walk outside to a nearby building in this building's plan metres: from the exit to the other entrance. */
function outdoorWalk(next: NextBuilding, origin: Origin, floor: number): Outdoor {
  return {
    from: fromLngLat(origin, ...next.from),
    to: fromLngLat(origin, ...next.to),
    floor,
    label: `${next.name} · ${next.outdoor_m} m →`,
  }
}

/** Starting questions that fit this building's data (no toilet chip in a building without toilets). */
function suggest(plan: Plan, floorName: string): Suggestion[] {
  const has = (...types: string[]) => plan.spaces.some((space) => types.includes(space.room_type))
  const out: Suggestion[] = []
  if (has('toilet', 'bathroom')) out.push({ label: 'Toilet', prompt: 'Where is the nearest toilet?', icon: 'toilet' })
  if (plan.openings.some((opening) => opening.entrance)) out.push({ label: 'Way out', prompt: 'How do I get out of the building?', icon: 'exit' })
  out.push({ label: 'Step-free', prompt: 'I use a wheelchair. Please keep my routes step-free.', icon: 'access' })
  if (has('canteen', 'kitchen')) out.push({ label: 'Food', prompt: 'Where can I get something to eat?', icon: 'food' })
  if (plan.floors.length > 1) out.push({ label: 'This floor', prompt: `What is on the ${floorName.toLowerCase()}?`, icon: 'floor' })
  out.push({ label: 'Help', prompt: 'What can you help me with here?', icon: 'help' })
  return out.slice(0, 5)
}

/** Which way a step goes (plan frame, unit): from its start to its end, so where it takes you is straight ahead and
 * a short kink at the door doesn't turn the map. */
function headingAt(track: RouteTrack, from: number, to: number): [number, number] {
  const [x0, y0] = track.at(from).at
  const [x1, y1] = track.at(to).at
  const length = Math.hypot(x1 - x0, y1 - y0)
  return length > 1e-3 ? [(x1 - x0) / length, (y1 - y0) / length] : track.at(from + 0.01).ahead
}
