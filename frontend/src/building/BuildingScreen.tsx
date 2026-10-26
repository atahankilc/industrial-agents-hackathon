// The building screen: the model fills the screen and a thin HUD sits on top. Top: back, the building's name and,
// on a phone, a floor chip (with "all floors" stacked); the theme, Preferences and the account are in the settings
// corner beside it (src/access/AccessLayer.tsx). Bottom right, over the plan's own buttons and only for whoever may
// change the building: the admin button, which turns the Edit mode on and off, and (the admin in access mode) the
// Building settings button above it — the Guide opens both too
// (backend/agents/tools.py open_edit_mode, open_building_settings). Bottom: the
// Guide, voice first — captions and the Core (src/building/Guide.tsx). One backend session per building; the plan comes from
// GET /sessions/{id}/plan.
// A building with a place on the map (`origin`) sits on the landing map, which follows the model's camera
// (src/map/bridge.ts), shown in its city: neighbours and their pins around it, a tap on a pin opens that one. A
// building without one stands alone on its own stage. The model takes over from the map's camera when it
// arrives and rises out of the ground; leaving fades it out.
// Answers move the camera to what they are about (`focus`): the rooms and items found, or a route — every floor
// stacked first when it crosses floors, then one step at a time once the user starts it; each step is read aloud
// and waits for "I'm there". The "you are here" figure tells the Guide where the user is. A route on to a nearby
// building ends in a Continue that opens that building and carries on there (arrival via sessionStorage).

import { ChevronLeft, ChevronsUpDown, Layers, LoaderCircle, PencilRuler, ShieldCheck } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { notify, useAccess } from '../access/auth'
import { BuildingSettings } from '../access/BuildingSettings'
import { useAccessRules } from '../access/useAccessRules'
import { capture, effective, sessionValues as toSession, setHere, setSpokenReplies, usePreferences } from '../access/preferences'
import { api, ApiError, ServiceError, type FleetObject, type GuideStep, type Issue, type LiveDevice, type NextBuilding, type PlacedLocation, type Plan, type Preferences } from '../api'
import { EditLayer } from '../edit/EditLayer'
import { LiveButton, LiveNotice, LivePanel, type Notice, type Placing } from '../live/LivePanel'
import { useLive, type LiveNews } from '../live/useLive'
import { ReferencePanel, useImageSize, type Trace } from '../edit/ReferencePanel'
import { EditBar } from '../edit/EditBar'
import { EditCard } from '../edit/EditCard'
import { useDraft } from '../edit/useDraft'
import { Placement } from '../map/Placement'
import '../import/import.css'
import { ImportScreen } from '../import/ImportScreen'
import { CATEGORY_LABEL, DARK, LIGHT } from '../plan/palette'
import { contains, prepareFloors } from '../plan/geometry'
import { PlanView, type Focus, type Insets, type Me, type Selected, type ViewMode } from '../plan/PlanView'
import { DEFAULT_SETTINGS } from '../plan/settings'
import { routeRuns } from '../dev/StoryLayer'
import { applyEvents, EMPTY_STORY, isEmpty, type DevEvent, type Outdoor, type Story } from '../dev/story'
import { addStep, settle, type Step } from '../ui/guideSteps'
import { follow, fromLngLat, hideBlocks, mapView, onShell, pinAt, pulse, settled, showBlocks, type Origin, type ShellBlock } from '../map/bridge'
import { groundColour } from '../map/style'
import { useTheme } from '../theme'
import { setScribeSession } from '../voice/scribe'
import type { Speech } from '../voice/tts'
import { useVoice, voiceSupported } from '../voice/useVoice'
import { Guide, type InfoCard, type Message, type Suggestion } from './Guide'
import { CameraWalk } from './CameraWalk'
import { grabFrame } from './frame'
import { Elsewhere } from './Elsewhere'
import { RouteBar, TripBar } from './RouteHud'
import { take } from './opening'
import { routeTrack, type RouteTrack } from './tracking'
import { askForMotion, useTracking } from './useTracking'
import './screen.css'
import './hud.css'

const WIDE_PX = 900
const TOP_PX = 64 // the HUD line
const GUIDE_PX = 250 // captions + Core on phones, until the Guide has measured itself
const EDIT_BAR_PX = 52 // the edit bar under the top line on phones (src/edit/edit.css .edit-bar)
const GUIDE_COL_PX = 360 // the Guide's column (bubble + dock) in the bottom-left corner of a wide screen
const ACTIONS_RIGHT_PX = 2 // the plan's own buttons (street view, compass, figure) and the admin button: one column under the floor rail, centred on it
const RAIL_PX = 72 // the floor rail on the right edge of a wide screen, with its margin
const CALLOUT_PX = 96 // room beyond the floor rail for the step callout beside a route's start (it reaches ~260px right)
const MOVE_PX = 56 // the trip pill under the top line (./RouteHud.tsx)
const OPEN_DELAY_MS = 1500 // the Guide opening a nearby building: its one-line reply shows first ...
const OPEN_MAX_MS = 15000 // ... and is heard to its end, but no longer than this
const TRACK_PX = 30 // its position line while tracking
// spoken commands while walking with the camera (anything else goes to the Guide with the frame)
const NEXT = /^\s*(next|weiter|nächste|sonraki|ileri|done|okay|ok|tamam|geldim|vardım|arrived|i'?m there|i'?m here|here|da|angekommen)\b/i
// starting the step-by-step guide of a route that is on the map
const START = /^\s*(start|go|let'?s go|begin|başla|basla|hadi|yola çık|los|starten)\b/i
// … also inside a short sentence ("okay, start the guide"), but not "start from the lobby"
const START_SAID = /\b(?:(?:start|begin)\b(?!\s+(?:from|at|in|with)\b)|let'?s go\b|başla|yola çık|starten\b)/i
// saying you reached a step inside a short sentence ("okay I'm there now", "tamam vardım"); unlike NEXT it also
// moves a route that was never started (the user walked its first step without pressing Start); "arrived" alone
// only first-person or as the first word, so "has my package arrived?" still reaches the Guide
const ARRIVED_SAID = /^\s*arrived(?!\p{L})|(?:^|[^\p{L}])(?:i'?m there|i'?m here|(?:i|we)(?: have|'ve)? arrived|got there|made it|next step|vardım|geldim|ulaştım|angekommen|bin da)(?!\p{L})/iu
const BACK = /^\s*(back|previous|zurück|geri|önceki)\b/i
const REPEAT = /^\s*(repeat|again|wiederholen|nochmal|tekrar)\b/i
// ending the route that is on the map ("stop", "cancel the route", "rotayı iptal et", "navigasyonu bitir")
const STOP = /^\s*(?:(?:stop|cancel|end|close|quit)(?:\s+(?:the\s+)?(?:route|directions|navigation|guide))?|(?:rotayı|navigasyonu|yol tarifini)\s+(?:iptal\s+et|kapat|bitir|durdur)|iptal(?:\s+et)?|beenden|abbrechen)\s*[.!]?\s*$/i
const WHERE_AM_I = 'Where am I? Use what my camera sees.'
/** the Edit mode's assistant in the Guide's card (backend/agents/builder.py) */
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

/** Shown once as the first chat line when a building opens right after it was saved in the Edit mode. */
const noteKey = (buildingId: string) => `note:${buildingId}`
/** A route coming over from a nearby building (route_to_building → Continue), picked up when this one opens. */
const arrivalKey = (buildingId: string) => `arrival:${buildingId}`
type Arrival = { entrance: string; destination: string; from: string | null; fromName: string; name: string; destinationName: string }
const STEP_WAIT_MS = 45_000 // the step-by-step guide listens this long for "I'm there" while the user walks
const FOCUS_ROOM_M = 14 // a found room is framed at least this wide, so its neighbours show around it
const FOCUS_STEP_M = 12
const LOCATED_HOLD_MS = 1600 // where the Guide placed you shows this long before the route from there
const MAYBE_AFTER_MS = 1800 // the answer shows this long before the rooms you might be in (your position not known)
const STEP_AHEAD_M = 10 // a step frames where you are and this much of the way ahead, not the whole stretch to its end
const FOCUS_ROUTE_M = 10

type ScreenProps = {
  buildingId: string
  /** where the building's metres start on the map, when the map is under this screen */
  origin: Origin | null
  /** fading out (another building, or the landing, is coming) */
  leaving: boolean
  onBack: () => void
  onOpen: (buildingId: string) => void
  /** open straight into the Edit mode (a building just created from floor plans: ImportScreen) */
  startEditing?: boolean
}

export function BuildingScreen({ buildingId, origin, leaving, onBack, onOpen, startEditing = false }: ScreenProps) {
  const theme = useTheme()
  const palette = theme.dark ? DARK : LIGHT
  const viewport = useViewport()
  const wide = viewport.width >= WIDE_PX

  const [sessionId, setSessionId] = useState<string | null>(null)
  const [plan, setPlan] = useState<Plan | null>(null)
  const [error, setError] = useState<string | null>(null)
  // the Guide's height on a phone, measured by the Guide itself (`onHeight`)
  const [guideHeight, setGuideHeight] = useState(GUIDE_PX)
  const [floor, setFloor] = useState(0)
  const [stacked, setStacked] = useState(false)
  const [selected, setSelected] = useState<Selected | null>(null)
  const [messages, setMessages] = useState<Message[]>(() => {
    const note = sessionStorage.getItem(noteKey(buildingId))
    return note ? [{ role: 'note', text: note }] : []
  })
  // access mode (src/access/): who is signed in, and the building settings sheet (admin)
  const access = useAccess()
  // who may change the building: its admin in access mode, anyone without it (editing works on a copy); nobody
  // until /config (and a signed-in viewer's /me) has answered, so ?edit=1 never shows the Edit mode to the wrong one
  const mayChange = !access.checking && (!access.mode || access.admin)
  // the admin in access mode also sets who may go where: the Access tool, and the Building settings button
  const admin = access.mode && access.admin
  // the Edit mode as asked for (the admin button, the Guide, ?edit=1) and as shown: only to whoever may change the
  // building — a link with ?edit=1 opens the plain building for anyone else, and the admin's once /me says so
  const [editAsked, setEditing] = useState(startEditing)
  const editing = editAsked && mayChange
  // Edit mode (src/edit/): the model becomes the draft copy's, handles sit on it, the edit card takes the Guide's place
  // the copy is only asked for once that check is over, so a non-admin's ?edit=1 never requests one
  const draft = useDraft(buildingId, editing, admin)
  // the Building settings sheet (admin): the shield button, the Access tool or the Guide open it
  const [settingsOpen, setSettingsOpen] = useState(false)
  // the access rules, shared by the Access tool and the Building settings sheet
  const accessRules = useAccessRules(buildingId, admin && (editing || settingsOpen))
  // "Edit position": the saved building's map placement, moved / turned / scaled again (one undoable step)
  const [placingOnMap, setPlacingOnMap] = useState(false)
  const [addingFloor, setAddingFloor] = useState(false) // "Add a floor": an import into this draft
  const placedAt = (draft.state?.building.building as { location?: PlacedLocation } | undefined)?.location
  const align = useRef<SVGGElement>(null)
  // the import's plan beside the editor (edit/ReferencePanel.tsx): open unless closed before, remembered per browser
  const [referenceOpen, setReferenceOpen] = useState(() => {
    try {
      return localStorage.getItem('edit.referenceOpen') !== 'false'
    } catch {
      return true
    }
  })
  const showReference = (open: boolean) => {
    setReferenceOpen(open)
    try {
      localStorage.setItem('edit.referenceOpen', String(open))
    } catch {
      // private mode: just not remembered
    }
  }
  const [trace, setTrace] = useState<Trace>({ on: false, opacity: 0.4 })
  // a request the Guide handed over with open_edit_mode, sent to the Builder once the draft is open
  const handOver = useRef<{ text: string; spoken: boolean } | null>(null)
  // a nearby building the Guide opened (open_nearby_building), gone to once its reply has been said
  const opening = useRef<{ go: () => void; at: number } | null>(null)
  const [pending, setPending] = useState(false)
  const [popover, setPopover] = useState<'floors' | null>(null)
  const preferences = usePreferences()
  const [objects, setObjects] = useState<FleetObject[]>([])
  const pollNow = useRef<() => void>(() => undefined)
  // the step the route bar (./RouteHud.tsx) shows, for the route answer it belongs to (a new answer starts at step 1)
  const [moveAt, setMoveAt] = useState({ key: -1, index: 0 })
  // walking the route with the camera (CameraWalk); `muted` stops it reading each step aloud
  const [walking, setWalking] = useState(false)
  const [muted, setMuted] = useState(false)
  // live tracking along the route (useTracking): counted steps between fixes
  const [tracking, setTracking] = useState(false)
  const cameraVideo = useRef<HTMLVideoElement>(null)
  const [look, setLook] = useState<ViewMode>('3d') // tilted, or flat once the user tilts straight down
  // what the camera frames (an answer's rooms, items or route part), and the "you are here" figure
  const [focus, setFocus] = useState<Focus | null>(null)
  const focusKey = useRef(0)
  const frameOn = (points: [number, number, number][], span: number, heading?: [number, number]) => setFocus({ key: ++focusKey.current, points, span, heading })
  const [me, setMe] = useState<Me | null>(null)
  // the route answer whose step-by-step guide was started (Start, or "start"); a new answer ends it
  const [guideKey, setGuideKey] = useState(-1)
  // the route answer shown as an overview (only its floors stacked); picking a floor or Start ends it
  const [overviewKey, setOverviewKey] = useState(-1)
  // the step the Guide just moved the card to: its reply already covers it, so it isn't read out again
  const quietStep = useRef<number | null>(null)
  // an answer held back until you have seen where you were placed, or the "you might be here" rooms after one
  const answerTimer = useRef<number | undefined>(undefined)
  useEffect(() => () => clearTimeout(answerTimer.current), [])

  useEffect(() => sessionStorage.removeItem(noteKey(buildingId)), [buildingId])

  // plan display settings, and the answer drawn on the plan
  const settings = DEFAULT_SETTINGS
  const [story, setStory] = useState<Story>(EMPTY_STORY)
  const storyRef = useRef(story)
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
  // the Preferences sheet offers this building's own preferences beside the general ones while it is on screen
  useEffect(() => {
    if (!plan) return
    const roomTypes = [...new Set(plan.spaces.map((space) => space.room_type).filter(Boolean))].sort()
    setHere({ id: buildingId, name: plan.building.name, roomTypes, spaceName: (id) => plan.spaces.find((space) => space.id === id)?.name })
    return () => setHere(null)
  }, [plan, buildingId])
  const sessionValues = useMemo(() => JSON.stringify(effective(preferences, buildingId)), [preferences, buildingId])
  const autoCapture = preferences.remember && preferences.auto_capture
  // the last values sent to this session: a field they had and the store no longer has goes as "not set"
  const sent = useRef<{ session: string; values: Preferences } | null>(null)
  useEffect(() => {
    if (!access.mode || !sessionId) return
    const timer = setTimeout(() => {
      const now = JSON.parse(sessionValues) as Preferences
      const values = toSession(sent.current?.session === sessionId ? sent.current.values : null, now)
      sent.current = { session: sessionId, values: now }
      api.sessionPreferences(sessionId, values, autoCapture).catch(() => undefined)
    }, 150)
    return () => clearTimeout(timer)
  }, [access.mode, sessionId, sessionValues, autoCapture, access.version])

  // the Edit mode works on one floor, seen from above (PlanView topDown): its handles sit on that floor's plan;
  // leaving it brings back all floors if they were stacked before
  const loaded = plan !== null
  const stackedBefore = useRef<boolean | null>(null)
  useEffect(() => {
    if (!loaded) return
    if (editing) {
      setStacked((was) => {
        stackedBefore.current ??= was
        return false
      })
    } else if (stackedBefore.current !== null) {
      setStacked(stackedBefore.current)
      stackedBefore.current = null
    }
  }, [editing, loaded])

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
  // the living building (src/live/): connected things polled while the screen shows the building, the panel with
  // its demo controls, a tap that puts something down, and notices when the route on the map has to change
  const [liveOpen, setLiveOpen] = useState(false)
  const [placing, setPlacing] = useState<Placing>(null)
  const [liveFocus, setLiveFocus] = useState<string | null>(null)
  const [notice, setNotice] = useState<Notice | null>(null)
  const noticeKey = useRef(0)
  const dismissed = useRef(new Set<string>())
  const onLiveNews = (news: LiveNews) => {
    if (news.reroute) {
      const wasGuiding = guiding
      onEvents([news.reroute])
      if (wasGuiding) {
        setGuideKey(storyRef.current.key) // the step guide goes on, on the new route
        quietStep.current = null
      }
      setNotice({ kind: 'reroute', message: news.reroute.message, key: ++noticeKey.current })
      setMessages((list) => [...list, { role: 'note', text: news.reroute!.message }])
      if ((guiding || walking) && !muted) speak(news.reroute.message)
    } else if (news.alert && !dismissed.current.has(news.alert.message)) {
      setNotice({ kind: 'alert', message: news.alert.message, key: ++noticeKey.current })
    } else if (news.suggestion && !dismissed.current.has(news.suggestion.message)) {
      setNotice((shown) => (shown?.message === news.suggestion!.message ? shown : { kind: 'suggestion', message: news.suggestion!.message, key: ++noticeKey.current }))
    }
  }
  const { live, pollNow: pollLive } = useLive(buildingId, sessionId, hasPlan && !editing, onLiveNews)
  // a reroute notice goes by itself after a while; an alert or a suggestion stays until dismissed or taken
  useEffect(() => {
    if (notice?.kind !== 'reroute') return
    const timer = setTimeout(() => setNotice((shown) => (shown?.key === notice.key ? null : shown)), 9000)
    return () => clearTimeout(timer)
  }, [notice])
  const liveControl = (action: 'speed' | 'pause' | 'resume' | 'clear' | 'block_route', value?: number) => {
    void api
      .liveControl({ building: buildingId, action, value, session_id: action === 'block_route' ? sessionId ?? undefined : undefined })
      .then(() => pollLive())
      .catch((reason) => setMessages((list) => [...list, { role: 'note', text: `Live: ${reason instanceof Error ? reason.message : String(reason)}` }]))
  }
  const focusDevice = (item: LiveDevice) => {
    setLiveFocus(item.id)
    if (item.position.floor === null) return
    setFloor(item.position.floor)
    setStacked(false)
    frameOn([[item.position.x, item.position.y, item.position.floor]], FOCUS_ROOM_M)
  }
  /** Show a new answer and take the camera to it: a route whole (when it crosses floors, only its floors, stacked:
   * the overview), or the rooms and items found (their floor, zoomed to them). */
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
      setOverviewKey(next.key)
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
    // the Guide opened the Building settings: shown to whoever may change the building (the admin button's people)
    if (events.some((event) => event.type === 'settings')) {
      if (admin) setSettingsOpen(true)
      else setMessages((list) => [...list, { role: 'note', text: access.mode ? 'Building settings need its admin account.' : 'Building settings come with sign-in.' }])
    }
    // the Guide opened a nearby building: a route to it (in this answer or already on the map) goes on there, like
    // its Continue; once the reply has been read and heard (the voice watch below)
    const opened = events.findLast((event) => event.type === 'open_building')
    if (opened?.type === 'open_building' && !editing) {
      const routed = events.findLast((event) => event.type === 'route' && !!event.next_building)
      const next = (routed?.type === 'route' ? routed.next_building : null) ?? storyRef.current.route?.next ?? null
      setMessages((list) => [...list, { role: 'note', text: `Opening ${opened.name}…` }])
      opening.current = { go: () => (next?.building === opened.building ? continueTo(next) : onOpen(opened.building)), at: Date.now() }
    }
    // access mode: what the Guide heard you prefer, remembered when you let it
    for (const event of events) {
      if (event.type === 'preference' && access.mode) capture(event.scope, event.values, buildingId, (id) => plan?.spaces.find((space) => space.id === id)?.name)
    }
    // the user told the Guide where they are: the figure stands there, and the map goes to it. When that is news
    // (the app didn't know, or had them elsewhere), the answer in the same reply (a route from there) follows after
    // LOCATED_HOLD_MS, so you first see where you were placed; otherwise the answer is framed straight away, below
    clearTimeout(answerTimer.current)
    const located = events.find((event) => event.type === 'location')
    const room = located?.type === 'location' ? plan?.spaces.find((space) => space.id === located.space_id) : undefined
    const news = !!room && room.id !== me?.space
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
    // the Guide ended the route (end_route): when nothing in this answer comes after it, the walk is over and the
    // figure goes where the user is now (the session put them there already)
    const ends = events.findLastIndex((event) => event.type === 'route_end')
    const ended = events[ends]
    if (ended?.type === 'route_end' && route && !events.slice(ends).some((event) => event.type === 'route')) {
      endRoute(ended.arrived, { at: ended.space_id ?? null, known: true })
      present(applyEvents(storyRef.current, events.slice(ends + 1)))
      return
    }
    const answer = applyEvents(storyRef.current, events)
    const fresh = answer.key !== storyRef.current.key && !isEmpty(answer) // this reply shows something new
    if (news && fresh) answerTimer.current = window.setTimeout(() => present(answer), LOCATED_HOLD_MS)
    else present(answer)
    // your position was needed but not known: once the answer has been seen, where you might be (the Guide's
    // guesses, else the entrances); a tap on one stands you there
    const maybe = room ? undefined : events.findLast((event) => event.type === 'maybe_here' && event.source === 'guide') ?? events.findLast((event) => event.type === 'maybe_here')
    if (maybe?.type === 'maybe_here') {
      const ids = maybe.space_ids
      answerTimer.current = window.setTimeout(() => showMaybe(ids), fresh ? MAYBE_AFTER_MS : 0)
    }
    // the Guide talked about another step of the route being followed: the step card (and the map) go there,
    // without reading the step out again over the reply (a new route in the same answer starts at step 1)
    const moved = events.findLast((event) => event.type === 'route_step')
    if (moved?.type === 'route_step' && route && !events.some((event) => event.type === 'route')) {
      const index = Math.max(0, Math.min(route.steps.length - 1, moved.index))
      quietStep.current = index
      setGuideKey(storyRef.current.key)
      onMove(index)
      setAskedAt(Date.now() + 1) // the Guide's words about that step stay up
    }
  }

  useEffect(() => {
    let cancelled = false
    // fetched since the tap (./opening.ts) and its floors built a frame at a time during the flight; shown once the
    // map's fly-in has landed, so the model takes over from it
    const preload = take(buildingId)
    const look = { wallHeight: settings.wallHeight, colours: settings.colours }
    const built = preload.promise.then(async (opened) => {
      if (!cancelled) await prepareFloors(opened.plan, palette, look)
      return opened
    })
    Promise.all([built, settled()])
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
      preload.release()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the look the first view will have; a later change rebuilds in PlanView
  }, [buildingId])

  // its block on the map breathes until the model is there (a failed open stops it too)
  const opened = plan !== null || error !== null
  useEffect(() => (origin && !opened ? pulse(buildingId) : undefined), [origin, opened, buildingId])

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
  const alone = !origin
  const mapCamera = useMemo(
    () => (origin ? { intro: () => mapView(origin), follow: leaving ? undefined : (view: Parameters<typeof follow>[1]) => follow(origin, view) } : undefined),
    [origin, leaving],
  )

  const routeSteps = useMemo(() => story.route?.steps ?? [], [story.route])
  const moving = routeSteps.length > 0
  // an alert or a suggestion is about the route on the map: it goes with the route
  useEffect(() => {
    if (!moving) setNotice((shown) => (shown && shown.kind !== 'reroute' ? null : shown))
  }, [moving])
  const moveIndex = moveAt.key === story.key ? Math.min(moveAt.index, routeSteps.length - 1) : 0
  const guiding = moving && guideKey === story.key
  // a route over several floors is first shown whole: only its floors, stacked, until it starts or a floor is picked
  const routeFloors = useMemo(() => (story.route ? [...new Set(routeRuns(story.route.line).map((run) => run.floor))].sort((a, b) => a - b) : []), [story.route])
  const overview = stacked && !guiding && overviewKey === story.key && routeFloors.length > 1
  // a stairs or lift step being walked: its two floors, stacked, with the riser between them
  const floorOf = useCallback((name: string | null) => plan?.floors.findIndex((item) => item.name === name) ?? -1, [plan])
  const ride = useMemo(() => (guiding && story.route ? rideAt(routeRuns(story.route.line), routeSteps, moveIndex, floorOf) : null), [guiding, story.route, routeSteps, moveIndex, floorOf])
  // on a phone the Guide's sheet grows with the answer that brought the route: framed again clear of it
  useEffect(() => {
    if (overview && !wide) setFocus((shown) => (shown ? { ...shown, key: ++focusKey.current } : shown))
    // only the sheet's height asks for it; the route's own framing happens in present()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [guideHeight])
  const track = useMemo(() => (story.route ? routeTrack(story.route.line, story.route.legs, story.route.steps.map((step) => step.legs ?? 1)) : null), [story.route])
  // while a step is walked the Guide's last answer gives the map room, until something new is asked or said
  const [movedAt, setMovedAt] = useState(0)
  const [askedAt, setAskedAt] = useState(0)
  const onMove = (index: number) => {
    setMoveAt({ key: story.key, index })
    setMovedAt(Date.now())
    // walking steps happen on their room's floor; a stairs or lift step changes it on the step after
    const step = routeSteps[index]
    const at = step && step.kind !== 'connector' && plan ? plan.floors.findIndex((item) => item.name === step.floor) : -1
    if (at >= 0 && (at !== floor || stacked)) {
      setFloor(at)
      setStacked(false)
    }
    // a ride: both floors stacked, framed on where it leaves the one and arrives on the other
    const rode = step?.kind === 'connector' && story.route ? rideAt(routeRuns(story.route.line), routeSteps, index, floorOf) : null
    if (rode) {
      setFloor(rode.floors[0])
      setStacked(true)
      frameOn(rode.points, FOCUS_STEP_M)
      return
    }
    // the camera follows you: where the step starts and the first metres of it
    if (track && step) {
      const from = track.starts[index] ?? 0
      const to = track.starts[index + 1] ?? from
      const ahead = Math.min(to, from + STEP_AHEAD_M)
      const points = Array.from({ length: 9 }, (_, i) => track.at(from + ((ahead - from) * i) / 8)).map(({ at: [x, y], floor: on }) => [x, y, on] as [number, number, number])
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
  /** The room the plan point is in (the smallest, on that floor), if any. */
  const roomAt = (at: [number, number], on: number) =>
    plan?.spaces.filter((space) => space.floor === on && contains(space.polygon, at[0], at[1])).sort((a, b) => a.area_m2 - b.area_m2)[0]
  /** The route is over — arrived, or ended or cancelled on the way: it leaves the map, the step guide, tracking and
   * the camera walk stop, and the "you are here" figure goes where the user is now: the destination when
   * `arrived`, else `at` (a room the Guide placed them in), else as far as the walk got (tracking's position, or
   * the last step they said they reached); otherwise it stays. `known`: the Guide ended it, so the session
   * knows already; else the app tells it (the route and the new position). */
  const endRoute = (arrived: boolean, { at = null, known = false }: { at?: string | null; known?: boolean } = {}) => {
    const route = storyRef.current.route
    const room = (id?: string | null) => (id ? plan?.spaces.find((space) => space.id === id) : undefined)
    let next: Me | null = null
    const placed = room(at) ?? (arrived ? room(route?.space_path[route.space_path.length - 1]) : undefined)
    if (placed) next = { at: placed.label, floor: placed.floor, space: placed.id, label: placed.name }
    else if (!known && tracking && position && track) {
      const there = track.at(position.metres)
      const inside = roomAt(there.at, there.floor)
      if (inside) next = { at: there.at, floor: there.floor, space: inside.id, label: inside.name }
    } else if (!known && guiding && moveIndex > 0) {
      const reached = room(routeSteps[moveIndex - 1]?.to_id)
      if (reached) next = { at: reached.label, floor: reached.floor, space: reached.id, label: reached.name }
    }
    setTracking(false)
    setWalking(false)
    setGuideKey(-1)
    present({ ...EMPTY_STORY, key: storyRef.current.key + 1 })
    if (next) {
      if (known) setMe(next)
      else placeMe(next)
    }
    if (!known && sessionId) void api.endRoute(sessionId).catch(() => undefined)
  }
  /** The user is at the last step: the route leaves the map, they stand at its end, and the chat says so. `say`:
   * also aloud. */
  const finishRoute = (say = false) => {
    const text = `You have arrived at ${routeSteps[routeSteps.length - 1]?.to ?? 'your destination'}.`
    endRoute(true)
    setMessages((list) => [...list, { role: 'note', text }])
    if (say) speak(text)
  }
  /** The user stopped the directions on the way (End directions, or "stop"). `say`: also aloud. */
  const cancelRoute = (say = false) => {
    endRoute(false)
    setMessages((list) => [...list, { role: 'note', text: 'Directions ended.' }])
    if (say) speak('Directions ended.')
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
      ? { ...track.at(position.metres), stale: position.stale, along: track.toLine(position.metres) }
      : stepping && track && to - from > 0.5 ? { ...track.at(from + 0.01), stale: false, along: track.toLine(from + 0.01) } : undefined
    // the step on the card, pinned where it is made (the arrival: at the end); before Start too, so the first move shows
    const pin = track ? track.at(routeSteps[moveIndex]?.kind === 'arrive' ? track.total : Math.min(track.total, from + 0.01)) : null
    const move = moving && pin ? { at: pin.at, floor: pin.floor, step: routeSteps[moveIndex], index: moveIndex } : undefined
    return { ...placed, step, you, move }
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
  /** Your position is not known: mark the rooms you might be in, with the answer still on, and frame them with it. */
  const showMaybe = (ids: string[]) => {
    if (!plan) return
    const rooms = plan.spaces.filter((space) => ids.includes(space.id))
    if (!rooms.length) return
    const next = { ...storyRef.current, maybe: rooms.map((space) => space.id) }
    storyRef.current = next
    setStory(next)
    const answer = plan.spaces.filter((space) => next.focus.includes(space.id))
    const points = [...rooms, ...answer].flatMap((space) => space.polygon.map(([x, y]) => [x, y, space.floor] as [number, number, number]))
    const floorsHit = new Set(points.map(([, , at]) => at))
    setFloor(rooms[0].floor)
    setStacked(floorsHit.size > 1)
    frameOn(points, FOCUS_ROOM_M)
  }
  /** A "you might be here" room tapped: you stand there, and the place the answer found is asked for from there. */
  const onMaybe = (id: string) => {
    const room = plan?.spaces.find((space) => space.id === id)
    if (!room) return
    const wanted = storyRef.current.focus.length === 1 && storyRef.current.focus[0] !== id ? plan?.spaces.find((space) => space.id === storyRef.current.focus[0]) : undefined
    placeMe({ at: room.label, floor: room.floor, space: room.id, label: room.name })
    const next = { ...storyRef.current, maybe: undefined }
    storyRef.current = next
    setStory(next)
    setFloor(room.floor)
    setStacked(false)
    frameOn(room.polygon.map(([x, y]) => [x, y, room.floor] as [number, number, number]), FOCUS_ROOM_M)
    if (wanted) void send(`Take me to ${wanted.name}.`, 'tap')
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

  const referenceShown = editing && draft.references.length > 0 && referenceOpen
  // on a wide screen the reference is a column on the right; the generated building keeps the middle
  const referenceWidth = referenceShown ? Math.round(Math.min(560, Math.max(320, viewport.width * 0.3))) : 0
  const baseInsets: Insets = wide
    ? { top: TOP_PX + 8 + (moving ? MOVE_PX + (followed ? TRACK_PX : 0) : 0), right: ACTIONS_RIGHT_PX, bottom: 24, left: 16 + GUIDE_COL_PX + 24 }
    : editing
      ? { top: TOP_PX + 8 + EDIT_BAR_PX, right: 0, bottom: guideHeight, left: 0 }
      : { top: TOP_PX + 8 + (moving ? MOVE_PX + (followed ? TRACK_PX : 0) : 0), right: 0, bottom: guideHeight, left: 0 }
  // beside the reference the building is framed in the space left of it
  const insets: Insets = referenceShown && wide ? { ...baseInsets, right: 16 + referenceWidth + 24 } : baseInsets

  // the whole building is centred on the screen: on a wide screen the Guide floats in the bottom-left corner, not
  // in a column, so it does not push the building right (the floor rail on the right is mirrored on the left); an
  // answer's own rooms still keep clear of it (`insets`). On a phone the plan's buttons stand on the Guide's top
  // edge (its measured height), so they never sit under a longer answer.
  const frameInsets: Insets = referenceShown
    ? insets
    : wide ? { ...insets, left: RAIL_PX, right: RAIL_PX } : insets
  // an answer's rooms and route: clear of the Guide column on the left (`insets`) and of the floor rail on the right
  // (`insets.right` only places the plan's buttons under the rail), with room for the start's step callout
  const focusInsets: Insets = wide ? { ...insets, right: RAIL_PX + CALLOUT_PX } : insets

  // while editing the model is the draft's (the original until the draft's plan has loaded), one floor at a time —
  // the floor chip and list follow it, so floors added in Edit mode can be picked
  const shownPlan = editing && draft.plan ? draft.plan : plan
  const current = shownPlan?.floors[floor]
  // the plan's buttons (figure, street view, compass), then the admin corner (Edit, and Building settings for the
  // admin in access mode): the Live button goes on top of them
  const liveBottom = insets.bottom + 16 + (44 + 10) * (3 + (!access.mode || access.admin ? (admin ? 2 : 1) : 0))
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
    if (words <= 4 && STOP.test(text)) return cancelRoute(!muted), true
    if (!guiding && (START.test(text) && words <= 3 || START_SAID.test(text) && words <= 6)) return startGuide(), true
    const step = (to: number) => onMove(Math.max(0, Math.min(routeSteps.length - 1, to)))
    // "I'm there": the card moves on (and the guide starts, if the user walked without pressing Start)
    if (guiding && words <= 3 && NEXT.test(text) || words <= 6 && ARRIVED_SAID.test(text)) {
      if (!guiding) setGuideKey(story.key)
      if (moveIndex < routeSteps.length - 1) step(moveIndex + 1)
      else if (story.route?.next) {
        // at the exit of a route into a nearby building: open it, as the Guide's open_nearby_building does
        const next = story.route.next
        if (!muted) speak(`You're at the exit. Opening ${next.name}.`)
        opening.current = { go: () => continueTo(next), at: Date.now() }
      }
      else finishRoute(!muted)
      return true
    }
    if (!guiding || words > 3) return false
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
    setAskedAt(Date.now() + 1)
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
        // whenever a route is on the map, so "I'm at the stairs" can move the card (show_route_step)
        routeStep: moving ? moveIndex : undefined,
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
      // ... and so does a new route, which ends in the offer to walk the user there ("say start")
      asked = via === 'tap' && (turn.reply.includes('?') || turn.events.some((event) => event.type === 'route'))
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
  // the building the Guide opened: after OPEN_DELAY_MS, once the voice is no longer saying the reply (or about to)
  const voiceState = useRef(voice.state)
  useEffect(() => {
    voiceState.current = voice.state
  }, [voice.state])
  useEffect(() => {
    const timer = window.setInterval(() => {
      const open = opening.current
      if (!open) return
      const waited = Date.now() - open.at
      const talking = voiceState.current === 'speaking' || voiceState.current === 'thinking'
      if (waited < OPEN_DELAY_MS || (talking && waited < OPEN_MAX_MS)) return
      opening.current = null
      open.go()
    }, 250)
    return () => window.clearInterval(timer)
  }, [])

  // one "Spoken replies": the Preferences sheet's (field `voice`) sets the Guide's own switch when it changes, and
  // the Guide menu's switch writes the preference back (useVoice keeps it on this device when remembering is off)
  const voicePreference = effective(preferences, buildingId).voice
  useEffect(() => {
    if (typeof voicePreference === 'boolean') voice.setSpeaks(voicePreference)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only when the preference changes
  }, [voicePreference])
  const speakReplies = (on: boolean) => {
    voice.setSpeaks(on)
    setSpokenReplies(buildingId, on)
  }

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
    setOverviewKey(-1) // "All floors" is every floor, also with a route on the map
    if (index !== 'all') setFloor(index)
    setSelected(null)
    setPopover(null)
  }

  // a floor that only the draft has (added in Edit mode) is gone once editing ends: back to one the building has
  if (!editing && plan && floor >= plan.floors.length) setFloor(0)
  const editFloorId = shownPlan?.floors[floor]?.id
  const editReference = draft.references.find((item) => item.floor_id === editFloorId) ?? null
  const traceSize = useImageSize(editReference?.image)
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
    <main className={`screen${origin ? ' on-map' : ''}${alone ? ' alone' : ''}${plan ? ' ready' : ''}${leaving ? ' leaving' : ''}${placing ? ' placing' : ''}`}>
      <div className="screen-stage" aria-hidden="true" />
      {shownPlan && (
        <PlanView
          plan={shownPlan}
          floor={floor}
          stacked={stacked}
          only={editing ? undefined : overview ? routeFloors : ride && stacked ? ride.floors : undefined}
          palette={palette}
          selected={editing ? (draft.selected && draft.selected.kind !== 'opening' ? { kind: draft.selected.kind, id: draft.selected.id } : null) : selected}
          insets={insets}
          frameInsets={frameInsets}
          focusInsets={focusInsets}
          // entering or leaving the Edit mode frames the floor again, straight down while editing
          fitKey={editing ? 1 : 0}
          topDown={editing}
          // the Access tool is about rooms: an item tapped picks the room it stands in
          onSelect={editing ? (picked) => {
            const asset = draft.tool === 'access' && picked?.kind === 'asset' ? draft.state?.building.assets.find((item) => item.id === picked.id) : undefined
            draft.setSelected(asset ? { kind: 'space', id: asset.space_id } : picked)
          } : setSelected}
          onPickFloor={(index) => {
            setFloor(index)
            setStacked(false)
          }}
          onTilt={setLook}
          spread={look === '3d'}
          settings={settings}
          story={editing ? EMPTY_STORY : shownStory}
          objects={access.mode && !editing ? objects : undefined}
          live={editing ? null : live}
          liveFocus={liveFocus}
          onLiveFocus={(id) => {
            setLiveFocus(id)
            if (id) setLiveOpen(false)
          }}
          focus={editing ? null : focus}
          // while guided, the dot on the route is you; the figure would stay behind at the start
          me={editing || guiding ? null : me}
          onMe={editing ? undefined : placeMe}
          onNext={story.route?.next && !editing ? () => continueTo(story.route!.next!) : undefined}
          onMaybe={editing ? undefined : onMaybe}
          align={editing && !stacked ? align : undefined}
          // the Door / Item tools place where you tap — on the floor you are on, or (all floors) on the one tapped,
          // which the view then steps onto
          onTap={editing && (draft.tool === 'door' || draft.tool === 'item') ? (tap) => {
            const floorId = shownPlan?.floors[tap.floor]?.id
            if (floorId) draft.placeAt(floorId, tap.at, tap.pixelsPerMetre)
            return true
          } : placing ? (tap) => {
            // the Live panel's Drop pallet / Park forklift: it goes where the plan was tapped
            const kind = placing
            setPlacing(null)
            void api
              .liveControl({ building: buildingId, action: 'drop', floor: tap.floor, x: tap.at[0], y: tap.at[1], kind })
              .then(() => pollLive())
              .catch(() => setMessages((list) => [...list, { role: 'note', text: `Put the ${kind} inside a room or corridor.` }]))
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
          restricted={admin ? accessRules.restricted : undefined}
          trace={trace.on && referenceShown && editReference && traceSize
            ? { image: editReference.image, ...traceSize, transform: editReference.transform, opacity: trace.opacity, adjust: trace.adjust }
            : null}
        />
      )}
      {editing && draft.references.length > 0 && (referenceOpen ? (
        <ReferencePanel
          reference={editReference}
          floorName={shownPlan?.floors[floor]?.name ?? ''}
          style={wide
            ? { right: 16, top: TOP_PX + 8 + EDIT_BAR_PX, maxHeight: `calc(100% - ${TOP_PX + 8 + EDIT_BAR_PX + 24}px)`, width: referenceWidth }
            : { left: 8, right: 8, top: TOP_PX + 8 + EDIT_BAR_PX, maxHeight: '42%' }}
          trace={trace}
          onTrace={setTrace}
          onAdjust={editFloorId ? (transform) => draft.onOps([{ op: 'set_reference', floor_id: editFloorId, transform }]) : undefined}
          onClose={() => {
            showReference(false)
            setTrace((current) => ({ ...current, on: false }))
          }}
        />
      ) : (
        <button type="button" className="hud-pill edit-reference-open" onClick={() => showReference(true)}>Show plan</button>
      ))}

      {/* "Opening the building…" from the tap until the model is there, the map's fly-in included; it fades in a
          beat late (screen.css), so a building that opens at once shows nothing */}
      {!plan && (
        <div className={`screen-status${error ? ' failed' : ''}`} role="status">
          {error ? (
            <p>Could not open this building. {error}</p>
          ) : (
            <p>
              <LoaderCircle size={16} strokeWidth={2.2} className="spin" aria-hidden="true" />
              Opening the building…
            </p>
          )}
        </div>
      )}

      <header className="hud-top">
        <button type="button" className="hud-btn" onClick={onBack} aria-label="All buildings">
          <ChevronLeft size={19} strokeWidth={2.2} />
        </button>
        <div className="hud-place">
          <h1>{plan?.building.name ?? 'Building'}</h1>
        </div>
        {shownPlan && shownPlan.floors.length > 1 && (
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
        <TripBar
          steps={routeSteps}
          index={moveIndex}
          lengthM={story.route?.length_m ?? null}
          profile={story.route?.profile ?? null}
          guiding={guiding}
          next={story.route?.next ?? null}
          onIndex={onMove}
          onClose={() => cancelRoute()}
          onCamera={() => setWalking(true)}
          tracking={tracking}
          position={followed ? position : null}
          track={track}
          onTrack={async () => {
            if (!tracking) await askForMotion() // iOS asks from this tap; a refusal leaves door and camera fixes
            setTracking((on) => !on)
          }}
        />
      )}

      {plan && popover && <div className="hud-scrim" onClick={() => setPopover(null)} />}
      {/* on a phone the floors open from the chip; on a wide screen they stay open on the right */}
      {shownPlan && shownPlan.floors.length > 1 && (
        <nav className={`hud-pop floors${popover === 'floors' ? ' open' : ''}`} aria-label="Floors" role="menu">
          <button type="button" role="menuitemradio" aria-checked={stacked} onClick={() => pickFloor('all')} title="All floors">
            <span className="tab"><Layers size={15} strokeWidth={2} /></span>
            <span className="name">All floors</span>
          </button>
          {[...shownPlan.floors.keys()].reverse().map((index) => (
            <button key={index} type="button" role="menuitemradio" aria-checked={!stacked && index === floor} onClick={() => pickFloor(index)} title={shownPlan.floors[index].name}>
              <span className="tab">{floorTab(shownPlan.floors[index].level)}</span>
              <span className="name">{shownPlan.floors[index].name}</span>
            </button>
          ))}
        </nav>
      )}
      {/* the admin buttons, on top of the column of the plan's buttons (PlanView: figure, street view, compass; just
          the compass while editing) — beside the floor rail on a wide screen, above the Guide on a phone. The pencil
          turns the Edit mode on and off; above it (the admin in access mode) the Building settings: access, members,
          objects. */}
      {plan && (!access.mode || access.admin) && (
        <div className="admin-corner" style={{ right: insets.right + 16, bottom: insets.bottom + 16 + (44 + 10) * (editing ? 1 : 3) }}>
          {admin && (
            <button
              type="button"
              className="admin-button"
              aria-pressed={settingsOpen}
              aria-label="Building settings"
              title="Building settings: access, members, objects"
              onClick={() => setSettingsOpen(true)}
            >
              <ShieldCheck size={19} strokeWidth={2} />
            </button>
          )}
          <button
            type="button"
            className="admin-button"
            aria-pressed={editing}
            aria-label={editing ? 'Stop editing' : 'Edit this building'}
            title={editing ? 'Stop editing' : 'Edit this building (on a copy)'}
            onClick={() => setEditing((on) => !on)}
          >
            <PencilRuler size={19} strokeWidth={2} />
          </button>
        </div>
      )}

      {/* the living building: its button on top of the column (over the admin button when there is one), its panel
          beside the column on a wide screen and above it on a phone, and the notice under the top line */}
      {plan && !editing && (
        <LiveButton
          live={live}
          open={liveOpen}
          onToggle={() => {
            setLiveOpen((open) => !open)
            setPlacing(null)
          }}
          style={{ right: insets.right + 16, bottom: liveBottom }}
        />
      )}
      {plan && !editing && liveOpen && (
        <LivePanel
          live={live}
          hasRoute={moving}
          placing={placing}
          focus={liveFocus}
          onPlace={setPlacing}
          onControl={liveControl}
          onFocus={focusDevice}
          onClose={() => {
            setLiveOpen(false)
            setPlacing(null)
          }}
          style={wide ? { right: insets.right + 16 + 44 + 12, bottom: Math.max(16, liveBottom - 200) } : { right: 16, bottom: liveBottom + 44 + 10, maxHeight: Math.max(220, viewport.height - (liveBottom + 44 + 10) - TOP_PX - 8) }}
        />
      )}
      {plan && notice && !editing && (
        <LiveNotice
          notice={notice}
          top={TOP_PX + 8 + (moving && !walking ? MOVE_PX + 8 : 0)}
          onTake={() => {
            setNotice(null)
            if (sessionId) void api.liveShorter(sessionId).then((reply) => onEvents(reply.events)).catch(() => undefined)
          }}
          onClose={() => {
            dismissed.current.add(notice.message)
            setNotice(null)
          }}
        />
      )}

      {access.mode && settingsOpen && (
        <BuildingSettings
          buildingId={buildingId}
          plan={plan}
          admin={access.admin}
          objects={objects}
          access={accessRules}
          onClose={() => setSettingsOpen(false)}
          onObjects={() => pollNow.current()}
          onShowOnPlan={() => {
            setSettingsOpen(false)
            setEditing(true)
            draft.setTool('access')
          }}
        />
      )}

      {editing && (
        <EditBar draft={draft} onFocusIssue={focusIssue} onDone={() => setEditing(false)} onSave={(name) => void saveDraft(name)} accessTool={admin}
          onPlace={placedAt?.origin ? () => setPlacingOnMap(true) : undefined} onAddFloor={() => setAddingFloor(true)}
          onStraighten={editFloorId && shownPlan && shownPlan.floors.length > 1 && floor > 0
            ? () => draft.onOps([{ op: 'straighten_floor', floor_id: editFloorId }]) : undefined} />
      )}
      {editing && addingFloor && draft.state && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 60 }}>
          <ImportScreen draft={{ id: draft.state.draft.id, name: draft.state.draft.name, levels: draft.state.building.floors.map((floor) => floor.level) }} onExit={() => setAddingFloor(false)}
            onDone={() => {
              const id = draft.state?.draft.id
              setAddingFloor(false)
              if (id) void api.draft(id).then(draft.adopt).catch((reason) => draft.setMessage(String(reason)))
            }} />
        </div>
      )}
      {editing && placingOnMap && draft.state && placedAt?.origin && (
        <main className="im" style={{ zIndex: 60 }}>
          <div className="im-inner">
            <button type="button" className="im-back" onClick={() => setPlacingOnMap(false)}>← Back to editing</button>
            <header className="im-head"><h1>Edit position</h1></header>
            <Placement draftId={draft.state.draft.id} location={placedAt} target={null} doneLabel="Save position"
              shape={editFloorId ? draft.state.building.spaces.filter((space) => space.floor_id === editFloorId)
                .map((space) => space.polygon as [number, number][]) : null}
              onDone={(next) => {
                setPlacingOnMap(false) // back to the editor first, whatever the answer holds
                if (next?.draft) draft.adopt(next)
              }} />
          </div>
        </main>
      )}

      {/* one assistant card: the Guide, or while editing the Builder (with the selection's inspector in it); it
          comes up once the building has loaded, not over the loading screen */}
      {!plan || !sessionId ? null : editing ? (
        <Guide
          onHeight={setGuideHeight}
          messages={draft.messages}
          pending={draft.asking}
          voice={{ ...voice, setSpeaks: speakReplies, supported: voiceSupported() }}
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
          card={draft.proposal || draft.selected || draft.tool !== 'select' ? <EditCard draft={draft} access={accessRules} onSettings={() => setSettingsOpen(true)} /> : undefined}
        />
      ) : (
        <Guide
          onHeight={setGuideHeight}
          messages={messages}
          pending={pending}
          voice={{ ...voice, setSpeaks: speakReplies, supported: voiceSupported() }}
          info={info}
          suggestions={suggestions}
          route={moving}
          quiet={guiding && movedAt >= askedAt}
          routeBar={
            moving && !walking ? (
              <RouteBar
                steps={routeSteps}
                index={moveIndex}
                guiding={guiding}
                next={story.route?.next ?? null}
                onStart={startGuide}
                onNext={() => onMove(Math.min(routeSteps.length - 1, moveIndex + 1))}
                onFinish={() => finishRoute()}
                onContinue={(next) => continueTo(next)}
              />
            ) : undefined
          }
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
          voice={{ ...voice, setSpeaks: speakReplies, supported: voiceSupported() }}
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

const OBJECTS_POLL_MS = 1000
const OBJECTS_POLL_MAX_MS = 15_000

/** Step `index` when it is a stairs or lift ride: the floors it leaves and reaches, and the route's points around
 * the change (the end of the run before, the start of the run after). Rides are followed along the route's runs in
 * order, each to the next run on the floor it reaches (`floorOf` its step's floor name), so a stairs step that climbs
 * several floors at once takes all of its changes. */
function rideAt(runs: ReturnType<typeof routeRuns>, steps: GuideStep[], index: number, floorOf: (name: string | null) => number): { floors: [number, number]; points: [number, number, number][] } | null {
  if (steps[index]?.kind !== 'connector') return null
  let at = 0 // the run the walk is on
  for (let s = 0; s <= index; s++) {
    if (steps[s].kind !== 'connector') continue
    const to = floorOf(steps[s].floor)
    let end = at + 1
    while (end < runs.length && (to >= 0 ? runs[end].floor !== to : runs[end].floor === runs[at].floor)) end++
    if (end >= runs.length) return null
    if (s === index) {
      const [before, after] = [runs[at], runs[end]]
      return {
        floors: [before.floor, after.floor],
        points: [
          ...before.points.slice(-3).map(([x, y]) => [x, y, before.floor] as [number, number, number]),
          ...after.points.slice(0, 3).map(([x, y]) => [x, y, after.floor] as [number, number, number]),
        ],
      }
    }
    at = end
  }
  return null
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

/** Starting questions that fit this building's data (no toilet chip in a building without toilets): the places
 * people look for first, each asked as "nearest" so the Guide routes from where the user is (find_nearest). Step-free
 * is a preference (the preferences form), not a question; food only where there is a canteen, since most buildings
 * are homes whose kitchens are private; three at most, the Guide card shows no more. */
function suggest(plan: Plan, floorName: string): Suggestion[] {
  const has = (...types: string[]) => plan.spaces.some((space) => types.includes(space.room_type))
  const out: Suggestion[] = []
  if (has('toilet', 'bathroom')) out.push({ label: 'Toilet', prompt: 'Take me to the nearest toilet.', icon: 'toilet' })
  if (plan.openings.some((opening) => opening.entrance)) out.push({ label: 'Way out', prompt: 'Take me to the nearest exit.', icon: 'exit' })
  if (plan.floors.length > 1 && plan.connectors.some((connector) => connector.kind === 'lift')) out.push({ label: 'Lift', prompt: 'Take me to the nearest lift.', icon: 'lift' })
  if (has('canteen')) out.push({ label: 'Canteen', prompt: 'Take me to the nearest canteen.', icon: 'food' })
  if (plan.floors.length > 1) out.push({ label: 'This floor', prompt: `What is on the ${floorName.toLowerCase()}?`, icon: 'floor' })
  return out.slice(0, 3)
}

/** Which way a step goes (plan frame, unit): from its start to its end, so where it takes you is straight ahead and
 * a short kink at the door doesn't turn the map. */
function headingAt(track: RouteTrack, from: number, to: number): [number, number] {
  const [x0, y0] = track.at(from).at
  const [x1, y1] = track.at(to).at
  const length = Math.hypot(x1 - x0, y1 - y0)
  return length > 1e-3 ? [(x1 - x0) / length, (y1 - y0) / length] : track.at(from + 0.01).ahead
}
