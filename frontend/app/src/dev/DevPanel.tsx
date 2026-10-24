// Dev tools (Vite dev server, or ?dev: BuildingScreen DEV_TOOLS): try every Guide capability by hand on the open
// building, without a language model. Each action runs one of the Guide's own tools through the backend's /dev
// endpoints (backend/devtools.py) and its map events go through the same story as a Guide reply (story.ts), so what
// the plan shows here is what an answer will show.
//
// Sections: Find (places and items) · Directions · Profile (who is walking) · Closures (close / reopen / add a
// door, impact before applying) · Display (plan switches) · History (every call, re-run, any tool by hand).

import {
  Accessibility, ArrowDownUp, Ban, Check, ChevronRight, Crosshair, History, LoaderCircle, MapPin, Navigation,
  RotateCcw, Search, SlidersHorizontal, X,
} from 'lucide-react'
import { useEffect, useId, useMemo, useRef, useState } from 'react'
import type { Plan } from '../api'
import type { Selected } from '../plan/PlanView'
import type { PlanSettings } from '../plan/settings'
import { devApi, type DevEvent, type DevState, type ToolDefinition, type ToolReply } from './devApi'
import { isEmpty, showAssets, showRooms, type Story } from './story'
import './dev.css'

export type LogEntry = { at: number; name: string; args: Record<string, unknown>; result: Record<string, unknown>; events: DevEvent[] }

type Props = {
  sessionId: string
  plan: Plan
  story: Story
  /** what is selected on the plan: offered as a place in every form */
  selected: Selected | null
  settings: PlanSettings
  onSettings: (settings: PlanSettings) => void
  onEvents: (events: DevEvent[]) => void
  onStory: (make: (story: Story) => Story) => void
  onReset: () => Promise<void>
  onClose: () => void
  log: LogEntry[]
  onLog: (entry: LogEntry) => void
  themeLabel: string
  onTheme: () => void
}

type Tab = 'find' | 'route' | 'profile' | 'closures' | 'display' | 'history'
const TABS: { key: Tab; label: string; icon: typeof Search }[] = [
  { key: 'find', label: 'Find', icon: Search },
  { key: 'route', label: 'Route', icon: Navigation },
  { key: 'profile', label: 'Profile', icon: Accessibility },
  { key: 'closures', label: 'Edits', icon: Ban },
  { key: 'display', label: 'View', icon: SlidersHorizontal },
  { key: 'history', label: 'Log', icon: History },
]
const TAB_KEY = 'ttyb-dev-tab'

/** A place a tool can take: a space id, an asset id, or "outside". */
export type Place = { id: string; name: string; detail: string }
const ENTRANCE: Place = { id: 'outside', name: 'Outside (main entrance)', detail: 'start from the street' }

type Call = (name: string, args?: Record<string, unknown>) => Promise<ToolReply>
type Shared = Props & { call: Call; places: Place[]; picked: Place | null; state: DevState | null; refresh: () => void }

const humanise = (text: string) => text.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())
/** Backend summaries name places as "Kitchen 0.07 [proc-…-S007] on Ground floor": drop the bracketed ids. */
const plain = (text: string) => humanise(text.replace(/\s*\[[^\]]*\]/g, ''))
const plural = (count: number, one: string, many = `${one}s`) => `${count} ${count === 1 ? one : many}`

function readTab(): Tab {
  try {
    const value = localStorage.getItem(TAB_KEY)
    return TABS.some((tab) => tab.key === value) ? (value as Tab) : 'route'
  } catch {
    return 'route'
  }
}

export function DevPanel(props: Props) {
  const { sessionId, plan, selected } = props
  const [tab, setTab] = useState<Tab>(readTab)
  const [state, setState] = useState<DevState | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [problem, setProblem] = useState<string | null>(null)
  // the directions form is shared: Find's "Route here" fills it
  const [routeTo, setRouteTo] = useState<Place | null>(null)

  useEffect(() => {
    try {
      localStorage.setItem(TAB_KEY, tab)
    } catch {
      // storage unavailable: the tab just isn't remembered
    }
  }, [tab])

  const refresh = () => void devApi.state(sessionId).then(setState).catch(() => setState(null))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(refresh, [sessionId, plan])

  const call: Call = async (name, args = {}) => {
    setBusy(name)
    setProblem(null)
    try {
      const reply = await devApi.tool(sessionId, name, args)
      props.onLog({ at: Date.now(), name, args, result: reply.result, events: reply.events })
      if (reply.events.length) props.onEvents(reply.events)
      if (reply.result.error) setProblem(String(reply.result.error))
      refresh()
      return reply
    } catch (reason) {
      const text = String(reason)
      // without persistence, sessions live in the backend's memory: a --reload restart forgets them
      const message = text.includes('unknown session') ? 'The backend restarted and forgot this session. Reload the page.' : text.includes('Failed to fetch') || text.includes('502') || text.includes('500') ? 'The backend is not answering. Is it running?' : text
      setProblem(message)
      const result = { error: message }
      props.onLog({ at: Date.now(), name, args, result, events: [] })
      return { result, events: [] }
    } finally {
      setBusy(null)
    }
  }

  const places = useMemo(() => {
    const out: Place[] = [ENTRANCE]
    for (const space of plan.spaces) {
      if (space.type === 'corridor') continue
      out.push({ id: space.id, name: space.name, detail: `${humanise(space.room_type || space.type)} · ${plan.floors[space.floor]?.name ?? ''}` })
    }
    return out
  }, [plan])

  // what is selected on the plan, as a place
  const picked = useMemo((): Place | null => {
    if (!selected) return null
    if (selected.kind === 'space') return places.find((place) => place.id === selected.id) ?? null
    const asset = plan.assets.find((item) => item.id === selected.id)
    if (!asset) return null
    const room = plan.spaces.find((space) => space.id === asset.space)
    return { id: asset.id, name: asset.name, detail: `${humanise(asset.type)} in ${room?.name ?? 'a room'}` }
  }, [selected, places, plan])

  const shared: Shared = { ...props, call, places, picked, state, refresh }

  return (
    <aside className="dev" aria-label="Dev tools">
      <header className="dev-head">
        <div>
          <strong>Dev tools</strong>
          <span>{plan.building.name}</span>
        </div>
        <button type="button" className="dev-icon" onClick={props.onClose} aria-label="Close dev tools" title="Close (` key)">
          <X size={16} strokeWidth={2.4} />
        </button>
      </header>

      <div className="dev-status">
        <span className="dev-chip" title="Routing profile">
          <Accessibility size={13} strokeWidth={2.4} aria-hidden="true" /> {state?.profile.summary ?? '…'}
        </span>
        {state && state.closed.length > 0 && (
          <span className="dev-chip warn">
            <Ban size={13} strokeWidth={2.4} aria-hidden="true" /> {plural(state.closed.length, 'closure')}
          </span>
        )}
        {busy && (
          <span className="dev-chip busy" aria-live="polite">
            <LoaderCircle size={13} strokeWidth={2.4} className="spin" aria-hidden="true" /> {humanise(busy)}…
          </span>
        )}
      </div>

      <nav className="dev-tabs" role="tablist" aria-label="Dev tool sections">
        {TABS.map(({ key, label, icon: Icon }) => (
          <button key={key} type="button" role="tab" aria-selected={tab === key} onClick={() => setTab(key)} title={label}>
            <Icon size={16} strokeWidth={2.2} aria-hidden="true" />
            <span>{label}</span>
          </button>
        ))}
      </nav>

      <div className="dev-body">
        {problem && (
          <div className="dev-problem" role="alert">
            <span>{problem}</span>
            <button type="button" className="dev-icon" onClick={() => setProblem(null)} aria-label="Dismiss">
              <X size={14} strokeWidth={2.4} />
            </button>
          </div>
        )}
        {/* every section stays mounted, so half-filled forms survive a look at another section */}
        <div hidden={tab !== 'find'}><FindSection {...shared} onRouteTo={(place) => { setRouteTo(place); setTab('route') }} /></div>
        <div hidden={tab !== 'route'}><RouteSection {...shared} routeTo={routeTo} /></div>
        <div hidden={tab !== 'profile'}><ProfileSection {...shared} /></div>
        <div hidden={tab !== 'closures'}><ClosuresSection {...shared} /></div>
        <div hidden={tab !== 'display'}><DisplaySection {...shared} /></div>
        <div hidden={tab !== 'history'}><HistorySection {...shared} /></div>
      </div>

      <footer className="dev-foot">
        <span>{describeStory(props.story)}</span>
        <button type="button" onClick={() => props.onStory((story) => ({ focus: [], assets: [], route: null, lost: [], key: story.key + 1 }))} disabled={isEmpty(props.story)}>
          Clear plan
        </button>
      </footer>
    </aside>
  )
}

function describeStory(story: Story) {
  if (isEmpty(story)) return 'Nothing shown on the plan'
  const parts = [
    story.route && `route ${story.route.length_m === null ? '' : `${Math.round(story.route.length_m)} m`}`.trim(),
    story.focus.length && !story.route && plural(story.focus.length, 'room'),
    story.assets.length && plural(story.assets.length, 'item'),
    story.lost.length && `${story.lost.length} without access`,
  ]
  return `On the plan: ${parts.filter(Boolean).join(' · ')}`
}

// ---------- shared pieces ----------

/** Search-as-you-type place field. Shows name + kind · floor, keyboard friendly, and offers what is selected on
 * the plan. */
function PlacePicker({ label, value, onChange, places, picked, placeholder }: {
  label: string
  value: Place | null
  onChange: (place: Place | null) => void
  places: Place[]
  picked: Place | null
  placeholder?: string
}) {
  const id = useId()
  const [text, setText] = useState('')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const box = useRef<HTMLDivElement>(null)
  const words = text.toLowerCase().split(/\s+/).filter(Boolean)
  const matches = useMemo(
    () => places.filter((place) => words.every((word) => `${place.name} ${place.detail} ${place.id}`.toLowerCase().includes(word))).slice(0, 8),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [places, text],
  )
  const choose = (place: Place) => {
    onChange(place)
    setText('')
    setOpen(false)
  }
  return (
    <div className="dev-field" ref={box} onBlur={(event) => !box.current?.contains(event.relatedTarget as Node) && setOpen(false)}>
      <label htmlFor={id}>{label}</label>
      {value ? (
        <div className="dev-place">
          <MapPin size={14} strokeWidth={2.4} aria-hidden="true" />
          <span>
            <strong>{value.name}</strong>
            <small>{value.detail}</small>
          </span>
          <button type="button" className="dev-icon" onClick={() => onChange(null)} aria-label={`Clear ${label}`}>
            <X size={14} strokeWidth={2.4} />
          </button>
        </div>
      ) : (
        <input
          id={id}
          value={text}
          placeholder={placeholder ?? 'Type a room, number or item…'}
          autoComplete="off"
          role="combobox"
          aria-expanded={open}
          aria-controls={`${id}-list`}
          onFocus={() => setOpen(true)}
          onChange={(event) => {
            setText(event.target.value)
            setActive(0)
            setOpen(true)
          }}
          onKeyDown={(event) => {
            if (event.key === 'ArrowDown') setActive((index) => Math.min(index + 1, matches.length - 1))
            else if (event.key === 'ArrowUp') setActive((index) => Math.max(index - 1, 0))
            else if (event.key === 'Enter' && matches[active]) choose(matches[active])
            else if (event.key === 'Escape') setOpen(false)
            else return
            event.preventDefault()
          }}
        />
      )}
      {!value && open && matches.length > 0 && (
        <ul className="dev-options" id={`${id}-list`} role="listbox">
          {matches.map((place, index) => (
            <li key={place.id} role="option" aria-selected={index === active}>
              <button type="button" onMouseDown={(event) => event.preventDefault()} onClick={() => choose(place)} onMouseEnter={() => setActive(index)}>
                <strong>{place.name}</strong>
                <small>{place.detail}</small>
              </button>
            </li>
          ))}
        </ul>
      )}
      {!value && picked && (
        <button type="button" className="dev-link" onClick={() => choose(picked)}>
          <Crosshair size={13} strokeWidth={2.4} aria-hidden="true" /> Use selected: {picked.name}
        </button>
      )}
    </div>
  )
}

function Details({ value, label = 'Details' }: { value: unknown; label?: string }) {
  if (value === null || value === undefined) return null
  return (
    <details className="dev-details">
      <summary>{label}</summary>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </details>
  )
}

function Section({ title, hint, children }: { title: string; hint: string; children: React.ReactNode }) {
  return (
    <section className="dev-section">
      <header>
        <h2>{title}</h2>
        <p>{hint}</p>
      </header>
      {children}
    </section>
  )
}

// ---------- Find ----------

type SearchHit = { kind: 'space' | 'asset'; id: string; name: string; room_type?: string; floor?: string; type?: string; in?: string }
type AssetHit = { asset_id: string; name: string; type: string; space_id: string; space_name: string }

function FindSection({ plan, call, onStory, onRouteTo, places }: Shared & { onRouteTo: (place: Place) => void }) {
  const [query, setQuery] = useState('')
  const [floor, setFloor] = useState('')
  const [rooms, setRooms] = useState<SearchHit[]>([])
  const [items, setItems] = useState<AssetHit[]>([])
  const [summary, setSummary] = useState<string | null>(null)
  const [raw, setRaw] = useState<unknown>(null)
  const level = floor === '' ? undefined : plan.floors[Number(floor)]?.level
  const floorId = floor === '' ? undefined : plan.floors[Number(floor)]?.id
  const where = floor === '' ? 'in the building' : `on ${plan.floors[Number(floor)]?.name}`

  // one-tap examples from what this building actually has
  const examples = useMemo(() => {
    const counts = new Map<string, number>()
    for (const asset of plan.assets) counts.set(asset.type, (counts.get(asset.type) ?? 0) + 1)
    const items = [...counts].sort((a, b) => a[1] - b[1]).slice(0, 4).map(([type]) => humanise(type).toLowerCase())
    const kinds = [...new Set(plan.spaces.map((space) => space.room_type).filter((type) => ['toilet', 'kitchen', 'canteen', 'lift', 'stairwell', 'print_room'].includes(type)))]
    return [...kinds.map((type) => humanise(type).toLowerCase()), ...items].slice(0, 7)
  }, [plan])

  const find = async (text = query) => {
    if (!text.trim()) return
    setQuery(text)
    const [search, locate] = [
      await call('search', { query: text, ...(level !== undefined ? { floor_level: level } : {}) }),
      await call('locate', { query: text, ...(floorId ? { floor_id: floorId } : {}) }),
    ]
    const hits = (search.result.results as SearchHit[] | undefined) ?? []
    const located = (locate.result.assets as AssetHit[] | undefined) ?? []
    const spaceHits = hits.filter((hit) => hit.kind === 'space')
    // locate understands kinds ("printers") better than search; fall back to search's items
    const itemHits: AssetHit[] = located.length
      ? located
      : hits.filter((hit) => hit.kind === 'asset').map((hit) => ({ asset_id: hit.id, name: hit.name, type: hit.type ?? '', space_id: plan.assets.find((asset) => asset.id === hit.id)?.space ?? '', space_name: hit.in ?? '' }))
    setRooms(spaceHits)
    setItems(itemHits)
    setRaw({ search: search.result, locate: locate.result })
    setSummary(spaceHits.length + itemHits.length === 0 ? `Nothing matches “${text}” ${where}.` : `${plural(spaceHits.length, 'room')} and ${plural(itemHits.length, 'item')} match “${text}” ${where}.`)
    if (itemHits.length) onStory((story) => showAssets(story, itemHits.map((item) => ({ id: item.asset_id, space: item.space_id }))))
    else if (spaceHits.length) onStory((story) => showRooms(story, spaceHits.slice(0, 40).map((hit) => hit.id)))
  }
  const count = async () => {
    const reply = await call('count_assets', { asset_type: query, ...(floorId ? { floor_id: floorId } : {}) })
    setRaw(reply.result)
    if (!reply.result.error) setSummary(`Count of “${query}” ${where}: ${String(reply.result.count ?? reply.result.total ?? '?')}.`)
  }
  const placeOf = (id: string) => places.find((place) => place.id === id)

  return (
    <Section title="Find places and items" hint="Search rooms by name, number or kind, and items by type or name. Results light up on the plan.">
      <form className="dev-row" onSubmit={(event) => { event.preventDefault(); void find() }}>
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="toilet, printer, 2.14…" aria-label="What to find" />
        <select value={floor} onChange={(event) => setFloor(event.target.value)} aria-label="Floor">
          <option value="">All floors</option>
          {plan.floors.map((item, index) => <option key={item.id} value={index}>{item.name}</option>)}
        </select>
      </form>
      <div className="dev-row">
        <button type="button" className="primary" onClick={() => void find()} disabled={!query.trim()}><Search size={14} strokeWidth={2.4} aria-hidden="true" /> Find</button>
        <button type="button" onClick={() => void count()} disabled={!query.trim()} title="How many items of this type">Count</button>
      </div>
      <div className="dev-examples" aria-label="Examples">
        {examples.map((example) => <button key={example} type="button" onClick={() => void find(example)}>{example}</button>)}
      </div>
      {summary && <p className="dev-answer">{summary}</p>}
      {rooms.length > 0 && (
        <div className="dev-group">
          <h3>Rooms</h3>
          <ul className="dev-list">
            {rooms.slice(0, 30).map((hit) => (
              <li key={hit.id}>
                <button type="button" className="dev-row-button" onClick={() => void call('show_on_map', { space_ids: [hit.id] })}>
                  <strong>{hit.name}</strong>
                  <small>{humanise(hit.room_type ?? '')} · {hit.floor}</small>
                </button>
                <button type="button" className="dev-mini" onClick={() => { const place = placeOf(hit.id); if (place) onRouteTo(place) }}>Route here <ChevronRight size={12} aria-hidden="true" /></button>
              </li>
            ))}
          </ul>
        </div>
      )}
      {items.length > 0 && (
        <div className="dev-group">
          <h3>Items</h3>
          <ul className="dev-list">
            {items.slice(0, 30).map((item) => (
              <li key={item.asset_id}>
                <button type="button" className="dev-row-button" onClick={() => onStory((story) => showAssets(story, [{ id: item.asset_id, space: item.space_id }]))}>
                  <strong>{item.name}</strong>
                  <small>{humanise(item.type)} · {item.space_name}</small>
                </button>
                <button type="button" className="dev-mini" onClick={() => onRouteTo({ id: item.asset_id, name: item.name, detail: `${humanise(item.type)} in ${item.space_name}` })}>Route here <ChevronRight size={12} aria-hidden="true" /></button>
              </li>
            ))}
          </ul>
        </div>
      )}
      <Details value={raw} label="Raw tool results" />
    </Section>
  )
}

// ---------- Directions ----------

type RouteOption = { id: string; name: string; floor: string; length_m: number | null }

function RouteSection({ call, onStory, places, picked, routeTo, state }: Shared & { routeTo: Place | null }) {
  const [from, setFrom] = useState<Place | null>(ENTRANCE)
  const [to, setTo] = useState<Place | null>(null)
  const [via, setVia] = useState<Place | null>(null)
  const [showVia, setShowVia] = useState(false)
  const [result, setResult] = useState<Record<string, unknown> | null>(null)
  useEffect(() => {
    if (routeTo) setTo(routeTo)
  }, [routeTo])

  const go = async (destination = to?.id) => {
    if (!from || !destination) return
    const reply = await call('find_route', { start: from.id, destination, ...(via ? { via: [via.id] } : {}) })
    setResult(reply.result)
  }
  const reachable = async () => {
    if (!from || from.id === 'outside') return
    const reply = await call('reachable_rooms', { start: from.id })
    setResult(reply.result)
    const rooms = reply.result.rooms as string[] | undefined
    if (rooms) onStory((story) => showRooms(story, rooms))
  }
  const options = (result?.options as RouteOption[] | undefined) ?? null
  const steps = (result?.steps as string[] | undefined) ?? null

  return (
    <Section title="Directions" hint="The shortest walk for the current profile and closures, drawn on the plan with its floor changes.">
      <div className="dev-route-form">
        <PlacePicker label="From" value={from} onChange={setFrom} places={places} picked={picked} />
        <button type="button" className="dev-icon swap" onClick={() => { setFrom(to); setTo(from) }} aria-label="Swap from and to" title="Swap">
          <ArrowDownUp size={15} strokeWidth={2.4} />
        </button>
        <PlacePicker label="To" value={to} onChange={setTo} places={places} picked={picked} />
        {showVia ? (
          <PlacePicker label="Stop on the way" value={via} onChange={(place) => { setVia(place); if (!place) setShowVia(false) }} places={places} picked={picked} />
        ) : (
          <button type="button" className="dev-link" onClick={() => setShowVia(true)}>+ Add a stop on the way</button>
        )}
      </div>
      <div className="dev-row">
        <button type="button" className="primary" onClick={() => void go()} disabled={!from || !to}><Navigation size={14} strokeWidth={2.4} aria-hidden="true" /> Show route</button>
        <button type="button" onClick={() => void reachable()} disabled={!from || from.id === 'outside'} title="Every room you can reach from the start with this profile">What can I reach from here?</button>
      </div>

      {options && (
        <div className="dev-group">
          <p className="dev-answer">Several places match. Which one?</p>
          <ul className="dev-list">
            {options.map((option) => (
              <li key={option.id}>
                <button type="button" className="dev-row-button" onClick={() => { setTo(places.find((place) => place.id === option.id) ?? { id: option.id, name: option.name, detail: option.floor }); void go(option.id) }}>
                  <strong>{option.name}</strong>
                  <small>{option.floor} · {option.length_m === null ? 'not reachable' : `${Math.round(option.length_m)} m away`}</small>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      {result?.reachable === true && (
        <div className="dev-card">
          <p className="dev-big">about {String(result.about_m ?? result.length_m)} m</p>
          <small>exactly {String(result.length_m)} m · {String(result.profile)}</small>
          {steps && <ol>{steps.map((step, index) => <li key={index}>{step}</li>)}</ol>}
        </div>
      )}
      {result?.reachable === false && (
        <p className="dev-answer warn">No way there with this profile and these closures. Check the Profile and Closures sections.</p>
      )}
      {typeof result?.count === 'number' && Array.isArray(result?.rooms) && (
        <p className="dev-answer">{plural(result.count as number, 'room')} reachable from {from?.name} ({String(result.profile)}).</p>
      )}
      {state?.profile_closed && state.profile_closed.length > 0 && (
        <p className="dev-hint">This profile treats {plural(state.profile_closed.length, 'door or lift', 'doors and lifts')} as closed.</p>
      )}
      <Details value={result} label="Raw tool result" />
    </Section>
  )
}

// ---------- Profile ----------

const PRESETS: { key: string; title: string; detail: string }[] = [
  { key: 'default', title: 'Anyone', detail: 'Stairs and lifts, any door' },
  { key: 'wheelchair', title: 'Wheelchair', detail: 'Step-free, doors at least 0.8 m (assumed)' },
  { key: 'pram', title: 'Pram', detail: 'Step-free, doors at least 0.8 m (assumed)' },
  { key: 'trolley', title: 'Trolley', detail: 'Step-free; set the trolley width below' },
  { key: 'no_lifts', title: 'No lifts', detail: 'Stairs only' },
  { key: 'forklift', title: 'Forklift', detail: 'Wide openings only, no stairs, no walkways' },
]

function ProfileSection({ state, call, onStory }: Shared) {
  const fields = state?.profile_fields
  const [width, setWidth] = useState('')
  const set = (args: Record<string, unknown>) => void call('set_profile', args)
  return (
    <Section title="Who is walking?" hint="Every later route follows this profile. Doors narrower than the minimum, and avoided lifts, count as closed.">
      <div className="dev-presets" role="radiogroup" aria-label="Profile">
        {PRESETS.map((preset) => (
          <button key={preset.key} type="button" role="radio" aria-checked={fields?.preset === preset.key} onClick={() => set({ preset: preset.key })}>
            <strong>{preset.title}</strong>
            <small>{preset.detail}</small>
            {fields?.preset === preset.key && <Check size={14} strokeWidth={3} className="tick" aria-hidden="true" />}
          </button>
        ))}
      </div>
      {fields && (
        <div className="dev-group">
          <h3>Fine-tune</h3>
          <label className="dev-switch"><input type="checkbox" checked={fields.step_free} onChange={(event) => set({ step_free: event.target.checked })} /><span>Step-free (no stairs, no steps)</span></label>
          <label className="dev-switch"><input type="checkbox" checked={fields.avoid_lifts} onChange={(event) => set({ avoid_lifts: event.target.checked })} /><span>Avoid lifts</span></label>
          <label className="dev-switch"><input type="checkbox" checked={fields.forklift} onChange={(event) => set({ forklift: event.target.checked })} /><span>Forklift rules</span></label>
          <form className="dev-row" onSubmit={(event) => { event.preventDefault(); set({ min_door_width_m: Number(width) || 0 }) }}>
            <label className="dev-inline">
              Minimum door width
              <span className="dev-unit">
                <input type="number" step="0.05" min="0" value={width} onChange={(event) => setWidth(event.target.value)} placeholder={fields.min_door_width_m ? String(fields.min_door_width_m) : 'none'} />
                m
              </span>
            </label>
            <button type="submit">Set</button>
          </form>
        </div>
      )}
      {state && (
        <div className="dev-card">
          <p><strong>Now:</strong> {state.profile.summary}</p>
          <p>{plural(state.profile_closed.length, 'door or lift', 'doors and lifts')} off-limits for this profile.</p>
          {state.unreachable === null ? (
            <p>The building has no entrance in the data.</p>
          ) : (
            <p>
              {plural(state.unreachable.length, 'room')} can't be reached from the entrance.{' '}
              {state.unreachable.length > 0 && (
                <button type="button" className="dev-link inline" onClick={() => onStory((story) => ({ focus: [], assets: [], route: null, lost: state.unreachable ?? [], key: story.key + 1 }))}>
                  Show them
                </button>
              )}
            </p>
          )}
        </div>
      )}
    </Section>
  )
}

// ---------- Closures ----------

type Proposal = { change_id: string; summary: string; effect: Record<string, unknown> }

/** The predicted effect of a change, in one or two sentences. */
function impact(effect: Record<string, unknown>) {
  const lines: string[] = []
  if (typeof effect.lost_access_count === 'number') {
    lines.push(effect.lost_access_count === 0 ? 'No room loses access.' : `${plural(effect.lost_access_count, 'room')} would lose access.`)
  }
  if (typeof effect.longer_routes_count === 'number' && effect.longer_routes_count > 0) {
    lines.push(`${plural(effect.longer_routes_count, 'route')} get longer, by up to ${Math.round(Number(effect.max_extra_m ?? 0))} m.`)
  }
  if (typeof effect.before_m === 'number') {
    lines.push(effect.still_reachable === false ? 'Your last route would no longer work.' : `Your last route: ${Math.round(effect.before_m)} m → ${Math.round(Number(effect.after_m))} m.`)
  }
  if (typeof effect.from === 'string') lines.push(`(Measured from ${plain(effect.from)}.)`)
  return lines
}

function ClosuresSection({ plan, state, call, onReset, refresh, places, picked }: Shared) {
  const [proposal, setProposal] = useState<Proposal | null>(null)
  const [doorA, setDoorA] = useState<Place | null>(null)
  const [doorB, setDoorB] = useState<Place | null>(null)
  const [confirmReset, setConfirmReset] = useState(false)
  const closed = new Set(state?.closed ?? [])
  const cores = useMemo(() => [...plan.connectors].sort((a, b) => a.kind.localeCompare(b.kind) || a.name.localeCompare(b.name, undefined, { numeric: true })), [plan])

  // impact is measured from the entrance room: the Guide's own default (the last route's start) can be "outside",
  // which compare_routes cannot start from
  const from = state?.entrance_space ? { start: state.entrance_space } : {}
  const propose = async (action: string, targets: string[]) => {
    const reply = await call('propose_change', { action, targets })
    if (!reply.result.change_id) return setProposal(null)
    const proposal = reply.result as unknown as Proposal
    if (typeof proposal.effect.lost_access_count !== 'number') {
      // fill in who loses access (this also previews it on the plan)
      const impact = await call('compare_routes', { change_id: proposal.change_id, ...from })
      if (!impact.result.error) proposal.effect = { ...proposal.effect, ...impact.result }
    }
    setProposal(proposal)
  }
  const preview = (id: string) => void call('compare_routes', { change_id: id, ...from })
  const apply = async (id: string) => {
    const reply = await call('apply_change', { change_id: id })
    setProposal(null)
    // the plan reloads with the closure; then show who lost access
    if (!reply.result.error) await call('compare_routes', { change_id: id, ...from })
  }
  const selectedRoom = picked && picked.id !== 'outside' && plan.spaces.some((space) => space.id === picked.id) ? picked : null

  return (
    <Section title="Closures and changes" hint="Close a lift, staircase or room (or add a door), see who is affected, then apply. Closed parts are hatched red on the plan.">
      {proposal && (
        <div className="dev-card accent" role="status">
          <p className="dev-big">{plain(proposal.summary)}?</p>
          {impact(proposal.effect).map((line) => <p key={line}>{line}</p>)}
          <div className="dev-row">
            <button type="button" className="primary" onClick={() => void apply(proposal.change_id)}><Check size={14} strokeWidth={2.6} aria-hidden="true" /> Apply</button>
            <button type="button" onClick={() => preview(proposal.change_id)} title="Grey dashed outlines: rooms that would lose access">Preview on plan</button>
            <button type="button" onClick={() => setProposal(null)}>Cancel</button>
          </div>
        </div>
      )}

      <div className="dev-group">
        <h3>Lifts and stairs</h3>
        <ul className="dev-list">
          {cores.map((connector) => {
            const isClosed = closed.has(connector.id)
            return (
              <li key={connector.id}>
                <span className="dev-row-button static">
                  <strong>{connector.name}</strong>
                  <small>{humanise(connector.kind)} · {connector.spaces.length} floors</small>
                </span>
                <span className={`dev-state ${isClosed ? 'closed' : 'open'}`}>{isClosed ? 'Closed' : 'Open'}</span>
                <button type="button" className="dev-mini" onClick={() => void propose(isClosed ? 'reopen' : 'close', [connector.id])}>
                  {isClosed ? 'Reopen…' : 'Close…'}
                </button>
              </li>
            )
          })}
          {cores.length === 0 && <li className="dev-hint">This building has no lifts or stairs.</li>}
        </ul>
      </div>

      <div className="dev-group">
        <h3>A room</h3>
        {selectedRoom ? (
          <div className="dev-row">
            <span className="dev-grow">{selectedRoom.name}</span>
            <button type="button" onClick={() => void propose(closed.has(selectedRoom.id) ? 'reopen' : 'close', [selectedRoom.id])}>
              {closed.has(selectedRoom.id) ? 'Reopen…' : 'Close…'}
            </button>
          </div>
        ) : (
          <p className="dev-hint">Tap a room on the plan to close or reopen it.</p>
        )}
      </div>

      <div className="dev-group">
        <h3>Add a door</h3>
        <PlacePicker label="Between" value={doorA} onChange={setDoorA} places={places.filter((place) => place.id !== 'outside')} picked={picked} />
        <PlacePicker label="and" value={doorB} onChange={setDoorB} places={places.filter((place) => place.id !== 'outside')} picked={picked} />
        <button type="button" onClick={() => doorA && doorB && void propose('add_door', [doorA.id, doorB.id])} disabled={!doorA || !doorB}>Propose door…</button>
      </div>

      {state && state.applied.length > 0 && (
        <div className="dev-group">
          <h3>Applied</h3>
          <ul className="dev-list">
            {state.applied.map((change) => (
              <li key={change.id}>
                <span className="dev-row-button static"><strong>{plain(change.summary)}</strong><small>{change.id}</small></span>
                <button type="button" className="dev-mini" onClick={() => preview(change.id)}>Impact</button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="dev-group">
        {confirmReset ? (
          <div className="dev-row">
            <span className="dev-grow">Undo every change and the profile?</span>
            <button type="button" className="danger" onClick={() => void onReset().then(() => { setConfirmReset(false); setProposal(null); refresh() })}>Yes, reset</button>
            <button type="button" onClick={() => setConfirmReset(false)}>No</button>
          </div>
        ) : (
          <button type="button" className="dev-link" onClick={() => setConfirmReset(true)}><RotateCcw size={13} strokeWidth={2.4} aria-hidden="true" /> Start over (reset the session)</button>
        )}
      </div>
    </Section>
  )
}

// ---------- Display ----------

function DisplaySection({ settings, onSettings, themeLabel, onTheme }: Shared) {
  const toggle = (label: string, on: boolean, change: (on: boolean) => void) => (
    <label className="dev-switch"><input type="checkbox" checked={on} onChange={(event) => change(event.target.checked)} /><span>{label}</span></label>
  )
  return (
    <Section title="Plan display" hint="How the plan is drawn. Only affects this browser tab.">
      {toggle('Furniture and equipment', settings.furniture === 'full', (on) => onSettings({ ...settings, furniture: on ? 'full' : 'off' }))}
      {toggle('Colour rooms by what they are for', settings.colours === 'use', (on) => onSettings({ ...settings, colours: on ? 'use' : 'clay' }))}
      {toggle('Pins for toilets, lifts, stairs, food, entrances', settings.pins, (on) => onSettings({ ...settings, pins: on }))}
      {toggle('Highlight the room under the mouse', settings.hover, (on) => onSettings({ ...settings, hover: on }))}
      <label className="dev-range">
        <span>Wall height <strong>{settings.wallHeight.toFixed(2)} m</strong></span>
        <input type="range" min="0.2" max="2.6" step="0.05" value={settings.wallHeight} onChange={(event) => onSettings({ ...settings, wallHeight: Number(event.target.value) })} />
      </label>
      <div className="dev-row">
        <button type="button" onClick={onTheme}>{themeLabel}</button>
      </div>
    </Section>
  )
}

// ---------- History ----------

/** One call in plain words. */
function describeCall(entry: LogEntry) {
  const { name, args, result } = entry
  if (result.error) return `${humanise(name)} failed`
  switch (name) {
    case 'find_route':
      return result.options ? `Route to “${String(args.destination)}”: several matches` : `Route ${String(args.start)} → ${String(args.destination)}: ${result.reachable ? `${String(result.about_m ?? result.length_m)} m` : 'no way'}`
    case 'search':
      return `Search “${String(args.query)}”: ${String(result.total ?? 0)} found`
    case 'locate':
      return `Locate “${String(args.query)}”: ${String(result.total ?? 0)} items`
    case 'set_profile':
      return `Profile: ${String(result.summary ?? '')}`
    case 'propose_change':
      return `Proposed: ${String(result.summary ?? '')}`
    case 'apply_change':
      return `Applied: ${String(result.applied ?? '')}`
    case 'compare_routes':
      return `Impact of ${String(args.change_id)}: ${String(result.lost_access_count ?? 0)} lose access`
    default:
      return humanise(name)
  }
}

function HistorySection({ log, call }: Shared) {
  const [tools, setTools] = useState<ToolDefinition[]>([])
  const [name, setName] = useState('building_overview')
  const [args, setArgs] = useState('{}')
  const [parseError, setParseError] = useState<string | null>(null)
  useEffect(() => void devApi.tools().then(setTools).catch(() => setTools([])), [])
  const tool = tools.find((item) => item.name === name)

  const pick = (next: string) => {
    setName(next)
    const schema = tools.find((item) => item.name === next)?.input_schema as { properties?: Record<string, { type?: string }> } | undefined
    setArgs(JSON.stringify(Object.fromEntries(Object.entries(schema?.properties ?? {}).map(([key, spec]) => [key, spec.type === 'array' ? [] : spec.type === 'object' ? {} : ''])), null, 2))
  }
  const run = () => {
    try {
      const parsed = JSON.parse(args || '{}') as Record<string, unknown>
      setParseError(null)
      void call(name, parsed)
    } catch {
      setParseError('That is not valid JSON.')
    }
  }

  return (
    <Section title="History" hint="Every tool call this session, newest first. Run one again, or call any Guide tool by hand.">
      {log.length === 0 && <p className="dev-hint">Nothing yet.</p>}
      <ul className="dev-log">
        {[...log].reverse().map((entry) => (
          <li key={entry.at + entry.name}>
            <details>
              <summary className={entry.result.error ? 'failed' : undefined}>
                <span>{describeCall(entry)}</span>
                <small>{new Date(entry.at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</small>
              </summary>
              <div className="dev-row">
                <button type="button" className="dev-mini" onClick={() => void call(entry.name, entry.args)}>Run again</button>
              </div>
              <pre>{JSON.stringify({ tool: entry.name, args: entry.args, result: entry.result, events: entry.events }, null, 2)}</pre>
            </details>
          </li>
        ))}
      </ul>
      <details className="dev-advanced">
        <summary>Advanced: call any tool</summary>
        <select value={name} onChange={(event) => pick(event.target.value)} aria-label="Tool">
          {tools.map((item) => <option key={item.name} value={item.name}>{item.name}</option>)}
        </select>
        {tool && <p className="dev-hint">{tool.description}</p>}
        <textarea value={args} onChange={(event) => setArgs(event.target.value)} rows={5} spellCheck={false} aria-label="Arguments (JSON)" />
        {parseError && <p className="dev-answer warn">{parseError}</p>}
        <button type="button" className="primary" onClick={run}>Run {name}</button>
      </details>
    </Section>
  )
}
