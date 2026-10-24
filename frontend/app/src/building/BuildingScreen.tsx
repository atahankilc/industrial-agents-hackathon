// The building screen: the model fills the screen and a thin HUD sits on top. Top: back, the building and floor,
// a floor chip (with "all floors" stacked) and a menu (edit, fit, theme, dev tools). Bottom: the Guide, voice first —
// captions and the Core (src/building/Guide.tsx). One backend session per building; the plan comes from
// GET /sessions/{id}/plan.
// A building with a place on the map (`origin`) sits on the landing map, which follows the model's camera
// (src/map/bridge.ts): shown in its city (neighbours and their pins around it, a tap on a pin opens that one) or
// alone (the map faded out, the model on its own stage). The model takes over from the map's camera when it
// arrives and rises out of the ground; leaving fades it out.

import { Box, Check, ChevronLeft, ChevronsUpDown, Ellipsis, Layers, Map as MapIcon, Moon, PencilRuler, Scan, Sun, SunMoon, Wrench } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, type Plan } from '../api'
import { EditMode } from '../edit/EditMode'
import { CATEGORY_LABEL, DARK, LIGHT } from '../plan/palette'
import { PlanView, type Insets, type Selected, type ViewMode } from '../plan/PlanView'
import { DEFAULT_SETTINGS } from '../plan/settings'
import { DevPanel, type LogEntry } from '../dev/DevPanel'
import { devApi, type DevEvent } from '../dev/devApi'
import { routeRuns } from '../dev/StoryLayer'
import { applyEvents, EMPTY_STORY, type Story } from '../dev/story'
import { addStep, settle, type Step } from '../ui/guideSteps'
import { follow, hideBlocks, mapView, pinAt, settled, showBlocks, type Origin } from '../map/bridge'
import { useTheme } from '../theme'
import { useVoice, voiceSupported } from '../voice/useVoice'
import { Guide, type InfoCard, type Message, type Suggestion } from './Guide'
import { CameraWalk } from './CameraWalk'
import { grabFrame } from './frame'
import { NextMove } from './NextMove'
import { take } from './opening'
import { routeTrack } from './tracking'
import { askForMotion, useTracking } from './useTracking'
import './screen.css'
import './hud.css'

const WIDE_PX = 900
const TOP_PX = 64 // the HUD line
const GUIDE_PX = 250 // captions + Core on phones
const PANEL_PX = 440 // the Guide panel on wide screens
const MOVE_PX = 132 // the next-move card under the top line on phones
const TRACK_PX = 30 // its position line while tracking
// spoken commands while walking with the camera (anything else goes to the Guide with the frame)
const NEXT = /^\s*(next|weiter|nächste|sonraki|ileri|done|okay|ok)\b/i
const BACK = /^\s*(back|previous|zurück|geri|önceki)\b/i
const REPEAT = /^\s*(repeat|again|wiederholen|nochmal|tekrar)\b/i
const WHERE_AM_I = 'Where am I? Use what my camera sees.'

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
  const [pending, setPending] = useState(false)
  const [popover, setPopover] = useState<'floors' | 'menu' | null>(null)
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
  /** Show a new answer: go to the floor where it starts (the route's start, else its first room) and fit it. */
  const present = (next: Story) => {
    const changed = next.key !== storyRef.current.key
    storyRef.current = next
    setStory(next)
    if (!plan || !changed) return
    const target = next.route ? routeRuns(next.route.line)[0]?.floor : plan.spaces.find((space) => next.focus.includes(space.id))?.floor
    if (target === undefined) return
    setFloor(target)
    setStacked(false)
    setFitKey((key) => key + 1)
  }
  const onEvents = (events: DevEvent[]) => {
    if (events.some((event) => event.type === 'change')) reloadPlan()
    // while tracking, the Guide placing you in a room of the route (e.g. "Where am I?" from the camera) is a fix,
    // not a new answer: the route stays and you are where it enters that room
    const route = storyRef.current.route
    const placed = tracking && route ? events.find((event) => event.type === 'highlight' && !event.style) : undefined
    if (placed?.type === 'highlight' && route) {
      const entered = route.steps.findIndex((step) => step.kind !== 'connector' && placed.space_ids.includes(step.to_id))
      if (entered >= 0) {
        fixAtStep(Math.min(entered + 1, route.steps.length - 1), 'camera')
        return
      }
    }
    present(applyEvents(storyRef.current, events))
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
      })
      .catch((reason) => !cancelled && setError(String(reason)))
    return () => {
      cancelled = true
      opening.release()
    }
  }, [buildingId])

  // the map's own block of this building gives way to the model while this screen is up
  useEffect(() => {
    if (!origin || !plan) return
    hideBlocks(buildingId, origin, (plan.outlines ?? []).flatMap((floor) => floor.map((polygon) => polygon[0] ?? [])))
  }, [buildingId, origin, plan])
  useEffect(() => () => showBlocks(buildingId), [buildingId])

  // the map under the model: where the model's camera starts, and the camera the map follows
  const alone = !origin || showing === 'alone'
  const mapCamera = useMemo(
    () => (origin ? { intro: () => mapView(origin), follow: leaving ? undefined : (view: Parameters<typeof follow>[1]) => follow(origin, view) } : undefined),
    [origin, leaving],
  )

  const routeSteps = useMemo(() => story.route?.steps ?? [], [story.route])
  const moving = routeSteps.length > 0
  const moveIndex = moveAt.key === story.key ? Math.min(moveAt.index, routeSteps.length - 1) : 0
  const onMove = (index: number) => {
    setMoveAt({ key: story.key, index })
    // walking steps happen on their room's floor; a stairs or lift step changes it on the step after
    const step = routeSteps[index]
    const at = step && step.kind !== 'connector' && plan ? plan.floors.findIndex((item) => item.name === step.floor) : -1
    if (at >= 0 && (at !== floor || stacked)) {
      setFloor(at)
      setStacked(false)
    }
  }

  const track = useMemo(() => (story.route ? routeTrack(story.route.line, story.route.legs) : null), [story.route])
  const kinds = useMemo(() => routeSteps.map((step) => step.kind), [routeSteps])
  const { position, fixAtStep } = useTracking({ track, routeKey: story.key, active: tracking && moving, step: moveIndex, kinds, onStep: onMove })
  const followed = tracking && moving && !!position && !!track
  const shownStory = useMemo(
    () => (position && track ? { ...story, you: { ...track.at(position.metres), stale: position.stale } } : story),
    [story, position, track],
  )

  const insets: Insets = wide
    ? { top: TOP_PX + 8 + (moving ? MOVE_PX + (followed ? TRACK_PX : 0) : 0), right: 24, bottom: 24, left: 16 + PANEL_PX + 24 + (devOpen ? DEV_PX : 0) }
    : { top: TOP_PX + 8 + (moving ? MOVE_PX + (followed ? TRACK_PX : 0) : 0), right: 0, bottom: GUIDE_PX, left: 0 }

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

  const send = async (text: string, spoken = false, photo?: string) => {
    if (!sessionId) return
    setSelected(null)
    setMessages((list) => [...list, { role: 'user', text, spoken }, { role: 'guide', text: '', live: true }])
    setPending(true)
    let key = 0
    const onLive = (update: (steps: Step[]) => Step[]) =>
      setMessages((list) => list.map((item) => (item.role === 'guide' && item.live ? { ...item, steps: update(item.steps ?? []) } : item)))
    try {
      const turn = await api.chatStream(sessionId, text, {
        channel: spoken ? 'voice' : 'text',
        photo,
        onStep: (step) => onLive((steps) => addStep(steps, step, key++)),
      })
      setMessages((list) =>
        list.map((item) =>
          item.role === 'guide' && item.live
            ? { role: 'guide', text: turn.reply, spoken, steps: settle(item.steps ?? []), route: turn.events.some((event) => event.type === 'route') }
            : item,
        ),
      )
      onEvents(turn.events)
      if (spoken || (walking && !muted)) voice.speak(turn.spoken ?? turn.reply)
    } catch (reason) {
      setMessages((list) => [
        ...list.filter((item) => !(item.role === 'guide' && item.live)),
        { role: 'note', text: `The Guide could not answer: ${String(reason)}` },
      ])
      voice.idle()
    } finally {
      setPending(false)
    }
  }

  const voice = useVoice({
    onUtterance: (text) => {
      if (!sessionId || pending) return false
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
        void send(text, true, grabFrame(cameraVideo.current))
        return true
      }
      void send(text, true)
      return true
    },
  })
  // one question, one answer: the Guide does not start listening again by itself after it speaks
  const { setHandsFree } = voice
  useEffect(() => setHandsFree(false), [setHandsFree])

  // walking with the camera: each step is read aloud when it comes up (not on mute)
  const { speak } = voice
  const stepText = walking && !muted ? routeSteps[moveIndex]?.text : undefined
  useEffect(() => {
    if (stepText) speak(`Step ${moveIndex + 1}. ${stepText}`)
  }, [stepText, moveIndex, speak])

  const pickFloor = (index: number | 'all') => {
    setStacked(index === 'all')
    if (index !== 'all') setFloor(index)
    setSelected(null)
    setPopover(null)
  }

  const ThemeIcon = THEME_ICON[theme.mode]

  if (editing)
    return (
      <main className="screen editing">
        <EditMode
          base={buildingId}
          palette={palette}
          onExit={() => setEditing(false)}
          onSaved={(saved, name) => {
            sessionStorage.setItem(noteKey(saved), `Saved “${name}” from the Edit mode — this is the edited building.`)
            onOpen(saved)
          }}
        />
      </main>
    )

  return (
    <main className={`screen${devOpen && wide ? ' dev-open' : ''}${origin ? ' on-map' : ''}${alone ? ' alone' : ''}${plan ? ' ready' : ''}${leaving ? ' leaving' : ''}`}>
      <div className="screen-stage" aria-hidden="true" />
      {plan && (
        <PlanView
          plan={plan}
          floor={floor}
          stacked={stacked}
          palette={palette}
          selected={selected}
          insets={insets}
          fitKey={fitKey}
          onSelect={setSelected}
          onPickFloor={(index) => {
            setFloor(index)
            setStacked(false)
          }}
          onTilt={setLook}
          spread={look === '3d'}
          settings={settings}
          story={shownStory}
          ground={alone}
          camera={mapCamera}
          onMiss={alone ? undefined : (x, y) => {
            const id = pinAt(x, y)
            if (id && id !== buildingId) onOpen(id)
            return Boolean(id)
          }}
        />
      )}
      {!plan && (
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
              {stacked ? 'All floors' : `${rooms} ${rooms === 1 ? 'room' : 'rooms'}`}
            </p>
          )}
        </div>
        {plan && plan.floors.length > 1 && (
          <button
            type="button"
            className="hud-chip"
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

      {moving && !walking && (
        <NextMove
          steps={routeSteps}
          index={moveIndex}
          lengthM={story.route?.length_m ?? null}
          profile={story.route?.profile ?? null}
          onIndex={onMove}
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
      {plan && popover === 'floors' && (
        <nav className="hud-pop floors" aria-label="Floors" role="menu">
          <button type="button" role="menuitemradio" aria-checked={stacked} onClick={() => pickFloor('all')}>
            <span className="tab"><Layers size={15} strokeWidth={2} /></span>
            All floors
          </button>
          {[...plan.floors.keys()].reverse().map((index) => (
            <button key={index} type="button" role="menuitemradio" aria-checked={!stacked && index === floor} onClick={() => pickFloor(index)}>
              <span className="tab">{floorTab(plan.floors[index].level)}</span>
              {plan.floors[index].name}
            </button>
          ))}
        </nav>
      )}
      {plan && popover === 'menu' && (
        <div className="hud-pop menu" role="menu">
          <button type="button" role="menuitem" onClick={() => { setEditing(true); setPopover(null) }} title="Edit this building (on a copy)">
            <PencilRuler size={17} strokeWidth={2} />
            Edit this building
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
          {DEV_TOOLS && (
            <button type="button" role="menuitem" onClick={() => { setDevOpen((open) => !open); setPopover(null) }}>
              <Wrench size={17} strokeWidth={2} />
              Dev tools
              {devOpen && <Check size={16} className="on" />}
            </button>
          )}
        </div>
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

      <Guide
        messages={messages}
        pending={pending}
        voice={{ ...voice, supported: voiceSupported() }}
        info={info}
        suggestions={suggestions}
        route={moving}
        onSend={(text) => void send(text)}
        onCloseInfo={() => setSelected(null)}
        onClear={() => {
          voice.stop()
          setMessages([])
        }}
      />

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
          onWhereAmI={(photo) => void send(WHERE_AM_I, false, photo)}
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
