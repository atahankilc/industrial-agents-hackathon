// App shell: one backend session per page, the point-cloud scene, the conversation, and a thin HUD.
// The Guide's UI events (GET /events, polled with a cursor) are the only thing that drives the scene, so the
// same view works when the conversation happens by voice through /v1/chat/completions.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, type Building, type ChatReply, type PointCloud, type SessionSummary, type UiEvent } from './api'
import { EditMode } from './edit/EditMode'
import { cloudExtent, type SpaceSets } from './scene/BuildingCloud'
import { Scene, type Focus } from './scene/Scene'
import { useTheme } from './theme'
import type { RouteCardData } from './ui/cards/Cards'
import { Chat, type Message, type SendOptions } from './ui/Chat'
import { addStep, followUps, settle } from './ui/guideSteps'

const DEFAULT_BUILDING = 'train/proc-campus-train-000'
const POLL_MS = 1500
const EXPLODE_M = 9
const EMPTY_SETS: SpaceSets = { highlight: [], lost: [], closed: [], route: [] }

type RouteState = {
  vertices: [number, number, number, number][]
  key: number
  from: string
  to: string
  length: number | null
  profile: string
}

function initialBuilding() {
  return new URLSearchParams(location.search).get('building') ?? DEFAULT_BUILDING
}

export default function App() {
  const { mode: themeMode, dark, cycle } = useTheme()
  const [buildings, setBuildings] = useState<Building[]>([])
  const [buildingId, setBuildingId] = useState(initialBuilding)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [cloud, setCloud] = useState<PointCloud | null>(null)
  const [summary, setSummary] = useState<SessionSummary | null>(null)
  const [llm, setLlm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [pending, setPending] = useState(false)
  const [sets, setSets] = useState<SpaceSets>(EMPTY_SETS)
  const [route, setRoute] = useState<RouteState | null>(null)
  const [focus, setFocus] = useState<Focus | null>(null)
  const [floorsOn, setFloorsOn] = useState<boolean[]>([])
  const [separated, setSeparated] = useState(false)
  const [emergeKey, setEmergeKey] = useState(0)
  const [mode, setMode] = useState<'view' | 'edit'>('view')
  const note = useRef<string | null>(null) // shown as the first chat line after the next building load
  const cursor = useRef(0)
  const nonce = useRef(0)

  const index = useMemo(() => {
    const spaces = new Map<string, number>()
    cloud?.spaces.forEach((space, i) => spaces.set(space.id, i))
    return spaces
  }, [cloud])
  const explode = separated ? EXPLODE_M : 0

  // ---------- session lifecycle ----------

  useEffect(() => {
    api.health().then((health) => setLlm(health.llm)).catch(() => setLlm(''))
    api.buildings().then(setBuildings).catch((reason) => setError(String(reason)))
  }, [])

  const reset = (next: PointCloud) => {
    setCloud(next)
    setFloorsOn(next.floors.map(() => true))
    setSets(EMPTY_SETS)
    setRoute(null)
    setFocus(null)
    setMessages(note.current ? [{ role: 'note', text: note.current }] : [])
    note.current = null
    cursor.current = 0
    setEmergeKey((key) => key + 1)
  }

  useEffect(() => {
    let cancelled = false
    setCloud(null)
    setError(null)
    const open = async () => {
      const id = sessionId ?? (await api.createSession(buildingId)).session_id
      if (sessionId && summary && summary.building !== buildingId) await api.switchBuilding(id, buildingId)
      const [points, state] = await Promise.all([api.points(id), api.session(id)])
      if (cancelled) return
      setSessionId(id)
      setSummary(state)
      reset(points)
    }
    open().catch((reason) => !cancelled && setError(String(reason)))
    return () => {
      cancelled = true
    }
    // sessionId/summary are read only to reuse the session when switching buildings
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [buildingId])

  // ---------- events → scene ----------

  const anchorOf = useCallback(
    (spaceIndex: number): [number, number, number] | null => {
      if (!cloud) return null
      const space = cloud.spaces[spaceIndex]
      if (!space) return null
      const floor = cloud.floors[space.floor]
      return [space.anchor[0] - cloud.center[0], floor.elevation_m + space.floor * explode, -space.anchor[1] - cloud.center[1]]
    },
    [cloud, explode],
  )

  const focusOn = useCallback((points: [number, number, number][], minimum = 14) => {
    if (points.length === 0) return
    const centre = [0, 1, 2].map((axis) => points.reduce((sum, p) => sum + p[axis], 0) / points.length) as [number, number, number]
    const spread = Math.max(...points.map((p) => Math.hypot(p[0] - centre[0], p[1] - centre[1], p[2] - centre[2])))
    setFocus({ nonce: ++nonce.current, target: centre, distance: Math.max(minimum, spread * 2.7) })
  }, [])

  const applyEvents = useCallback(
    (events: UiEvent[]) => {
      if (!cloud) return
      const toIndices = (ids: string[]) => ids.map((id) => index.get(id)).filter((i): i is number => i !== undefined)
      for (const event of events) {
        if (event.type === 'route' && event.vertices && event.vertices.length >= 2) {
          const spaces = toIndices(event.space_path)
          const vertices = event.vertices
          setRoute({
            vertices,
            key: ++nonce.current,
            from: cloud.spaces[spaces[0]]?.name ?? '',
            to: cloud.spaces[spaces[spaces.length - 1]]?.name ?? '',
            length: event.length_m ?? null,
            profile: event.profile ?? '',
          })
          setSets((current) => ({ ...current, route: spaces, highlight: [] }))
          setFloorsOn((current) => current.map((on, floor) => on || vertices.some((v) => v[3] === floor)))
          focusOn(vertices.map(([x, y, z, floor]) => [x, y + floor * explode, z]), 24)
        } else if (event.type === 'highlight') {
          const spaces = toIndices(event.space_ids)
          if (event.style === 'lost_access') {
            setSets((current) => ({ ...current, lost: spaces }))
          } else {
            setSets((current) => ({ ...current, highlight: spaces }))
            focusOn(spaces.map(anchorOf).filter((p): p is [number, number, number] => p !== null), 22)
          }
        } else if (event.type === 'change') {
          const spaces = toIndices(event.space_ids ?? event.targets)
          const reopen = event.summary.startsWith('reopen')
          setSets((current) => ({
            ...current,
            closed: reopen ? current.closed.filter((i) => !spaces.includes(i)) : [...new Set([...current.closed, ...spaces])],
            lost: [],
          }))
          setMessages((current) => [...current, { role: 'applied', text: event.summary }])
          if (event.summary.startsWith('add a door') && sessionId) api.points(sessionId).then(setCloud).catch(() => {})
        }
      }
    },
    [cloud, index, explode, anchorOf, focusOn, sessionId],
  )

  // Polls are chained, never concurrent: two overlapping polls would read the same cursor and replay events.
  const polling = useRef<Promise<void>>(Promise.resolve())
  const poll = useCallback(() => {
    polling.current = polling.current.then(async () => {
      if (!sessionId) return
      const { events, next } = await api.events(sessionId, cursor.current)
      cursor.current = next
      if (events.length) applyEvents(events)
    }).catch(() => {})
    return polling.current
  }, [sessionId, applyEvents])

  useEffect(() => {
    if (!sessionId || !cloud) return
    const timer = setInterval(() => void poll(), POLL_MS)
    return () => clearInterval(timer)
  }, [sessionId, cloud, poll])

  // Separating floors makes the building taller: re-frame it (only when nothing specific is in focus).
  useEffect(() => {
    if (!cloud || route || sets.highlight.length) return
    const { extent, top } = cloudExtent(cloud)
    const height = top + (cloud.floors.length - 1) * explode
    setFocus({ nonce: ++nonce.current, target: [0, height / 3, 0], distance: Math.hypot(extent, height / 2) * 2.6 })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [separated])

  // ---------- conversation ----------

  // The reply in progress is the one `live` message: steps stream into it, then the reply fills it in. (Change
  // notes polled meanwhile may land after it.)
  const updateLive = (update: (message: Message) => Message) =>
    setMessages((current) => current.map((message) => (message.live ? update(message) : message)))

  const routeCard = useCallback(
    (turn: ChatReply): RouteCardData | undefined => {
      const event = [...turn.events].reverse().find((item) => item.type === 'route')
      if (!cloud || event?.type !== 'route' || !event.legs?.length) return undefined
      const name = (id: string) => cloud.spaces[index.get(id) ?? -1]?.name ?? ''
      const floors = [...new Set(event.legs.map((leg) => leg.floor).filter((floor): floor is string => Boolean(floor)))]
      return {
        key: ++nonce.current,
        from: name(event.space_path[0]),
        to: name(event.space_path[event.space_path.length - 1]),
        length: event.length_m ?? null,
        profile: event.profile ?? '',
        floors,
        legs: event.legs,
        event,
      }
    },
    [cloud, index],
  )

  const send = async (text: string, options: SendOptions = {}): Promise<ChatReply | null> => {
    if (!sessionId) return null
    setMessages((current) => [
      ...current,
      { role: 'user', text, photo: Boolean(options.photo) },
      { role: 'guide', text: '', steps: [], live: true },
    ])
    setPending(true)
    let stepKey = 0
    try {
      const turn = await api.chatStream(sessionId, text, {
        ...options,
        onStep: (step) => {
          updateLive((message) => ({ ...message, steps: addStep(message.steps ?? [], step, stepKey++) }))
          if (step.kind === 'tool_done') void poll() // the map moves while the Guide is still writing
        },
      })
      await poll()
      const state = await api.session(sessionId)
      setSummary(state)
      const names = (ids: string[]) => ids.map((id) => cloud?.spaces[index.get(id) ?? -1]?.name).filter((n): n is string => Boolean(n))
      updateLive((message) => ({
        ...message,
        live: false,
        text: turn.reply,
        spoken: turn.spoken,
        steps: settle(message.steps ?? []),
        route: routeCard(turn),
        followups: followUps(turn, { names, stepFree: state.profile.step_free, pending: state.pending.length }),
      }))
      return turn
    } catch (reason) {
      setMessages((current) => [
        ...current.filter((message) => !message.live),
        { role: 'note', text: `Something went wrong: ${String(reason)}` },
      ])
      return null
    } finally {
      setPending(false)
    }
  }

  const showRoute = (card: RouteCardData) => applyEvents([card.event])

  // ---------- view ----------

  const floors = cloud?.floors ?? []
  const solo = floorsOn.filter(Boolean).length === 1 ? floorsOn.indexOf(true) : -1
  const showFloor = (floor: number | null) =>
    setFloorsOn(floors.map((_, i) => floor === null || i === floor))

  const onSaved = (building: string, name: string) => {
    note.current = `Saved “${name}” and switched to it — the conversation restarted on the edited building.`
    api.buildings().then(setBuildings).catch(() => {})
    setMode('view')
    setBuildingId(building)
  }

  return (
    <div className="app">
      {mode === 'edit' && <EditMode base={buildingId} dark={dark} onSaved={onSaved} />}
      {mode === 'view' && cloud && (
        <Scene
          cloud={cloud}
          dark={dark}
          sets={sets}
          floorsOn={floorsOn}
          explode={explode}
          density={1}
          emergeKey={emergeKey}
          route={route}
          focus={focus}
        />
      )}
      {mode === 'view' && !cloud && (
        <div className="loading">
          {error ? <p className="error">{error}</p> : <p className="muted pulse">Scanning building…</p>}
        </div>
      )}

      <header className="hud top">
        <div className="brand">
          <span className="mark" aria-hidden="true" />
          <div>
            <h1>{cloud?.building.name ?? 'Talk to your building'}</h1>
            <select
              aria-label="Building"
              value={buildingId}
              onChange={(event) => setBuildingId(event.target.value)}
            >
              {buildings.length === 0 && <option value={buildingId}>{buildingId}</option>}
              {buildings.map((building) => (
                <option key={building.id} value={building.id}>
                  {building.id}{building.name ? ` · ${building.name}` : ''}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="actions">
          <div className="mode-switch" role="group" aria-label="Mode">
            <button type="button" className={mode === 'view' ? 'on' : ''} onClick={() => setMode('view')}>View</button>
            <button type="button" className={mode === 'edit' ? 'on' : ''} onClick={() => setMode('edit')} disabled={!cloud}>Edit</button>
          </div>
          {llm && <span className="tag">{llm === 'offline' ? 'offline mode' : 'claude'}</span>}
          <button type="button" className="icon" onClick={() => setEmergeKey((key) => key + 1)} aria-label="Replay scan" title="Replay scan">
            <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="M13 8a5 5 0 1 1-1.5-3.6M13 2.5v3h-3" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" /></svg>
          </button>
          <button type="button" className="icon" onClick={cycle} aria-label={`Theme: ${themeMode}`} title={`Theme: ${themeMode}`}>
            <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
              <circle cx="8" cy="8" r="5.5" fill="none" stroke="currentColor" strokeWidth="1.4" />
              {themeMode !== 'light' && <path d="M8 2.5a5.5 5.5 0 0 1 0 11z" fill="currentColor" />}
              {themeMode === 'system' && <circle cx="8" cy="8" r="1.4" fill="currentColor" />}
            </svg>
          </button>
        </div>
      </header>

      {mode === 'view' && cloud && (
        <nav className="hud floors" aria-label="Floors">
          <button type="button" className={solo === -1 ? 'on' : ''} onClick={() => showFloor(null)}>All</button>
          {[...floors].map((floor, i) => ({ floor, i })).reverse().map(({ floor, i }) => (
            <button key={i} type="button" className={solo === i ? 'on' : ''} onClick={() => showFloor(solo === i ? null : i)} title={floor.name}>
              {floor.level}
            </button>
          ))}
          <span className="rule" />
          <button type="button" className={separated ? 'on' : ''} onClick={() => setSeparated((on) => !on)} title="Separate floors">
            <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M2 4.5 8 2l6 2.5L8 7zM2 8.5 8 11l6-2.5M2 12 8 14.5 14 12" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" /></svg>
          </button>
        </nav>
      )}

      {mode === 'view' && <footer className="hud status">
        {route && (
          <div className="route-line">
            <span className="label">Route</span>
            <span>{route.from} → {route.to}</span>
            {route.length !== null && <span className="muted">{Math.round(route.length)} m</span>}
          </div>
        )}
        {summary && (
          <div className="route-line">
            <span className="label">Profile</span>
            <span>{summary.profile.summary}</span>
            {summary.applied.length > 0 && <span className="muted">· {summary.applied.map((change) => change.summary).join(', ')}</span>}
          </div>
        )}
        {cloud?.building.attribution && <div className="attribution muted">{cloud.building.attribution}</div>}
      </footer>}

      {mode === 'view' && <Chat
        messages={messages}
        pending={pending}
        disabled={!sessionId || !cloud}
        profile={summary?.profile.summary ?? null}
        pendingChanges={summary?.pending ?? []}
        onSend={send}
        onShowRoute={showRoute}
      />}
    </div>
  )
}
