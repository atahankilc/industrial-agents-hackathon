// The building screen: the model fills the screen; the guide line on top names where you are; on the right edge
// the floor tabs (with "all floors" stacked) and the light/dark switch; the conversation floats
// at the bottom and only shows the latest exchange. One backend session per building; the plan comes from
// GET /sessions/{id}/plan.

import { ChevronLeft, Layers, Moon, Scan, Sun, SunMoon } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { api, type Plan } from '../api'
import { CATEGORY_LABEL, DARK, LIGHT } from '../plan/palette'
import { PlanView, type Insets, type Selected, type ViewMode } from '../plan/PlanView'
import { DEFAULT_SETTINGS } from '../plan/settings'
import { stepLabel } from '../ui/guideSteps'
import { useTheme } from '../theme'
import { hearOnce, say, voiceSupported } from '../voice/useVoice'
import { Conversation, type InfoCard, type Message, type Suggestion } from './Conversation'
import './screen.css'

const WIDE_PX = 900
const GUIDE_LINE_PX = 76
const CONTROLS_PX = 60
const ASK_PX = 84
const VOICE_LANG = 'en-US'

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
const THEME_LABEL = { system: 'Theme: follows the system', light: 'Theme: light', dark: 'Theme: dark' }

export function BuildingScreen({ buildingId, onBack }: { buildingId: string; onBack: () => void }) {
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
  const [messages, setMessages] = useState<Message[]>([])
  const [pending, setPending] = useState(false)
  const [listening, setListening] = useState(false)
  const [fitKey, setFitKey] = useState(0)
  const [look, setLook] = useState<ViewMode>('3d') // tilted, or flat once the user tilts straight down

  useEffect(() => {
    let cancelled = false
    api
      .createSession(buildingId)
      .then(async ({ session_id }) => {
        const next = await api.plan(session_id)
        if (cancelled) return
        setSessionId(session_id)
        setPlan(next)
        const ground = next.floors.findIndex((item) => item.level === 0)
        setFloor(ground >= 0 ? ground : 0)
      })
      .catch((reason) => !cancelled && setError(String(reason)))
    return () => {
      cancelled = true
    }
  }, [buildingId])

  const insets: Insets = wide
    ? { top: 16, right: CONTROLS_PX + 16, bottom: ASK_PX + 16, left: 16 }
    : { top: GUIDE_LINE_PX, right: CONTROLS_PX, bottom: ASK_PX + 40, left: 0 }

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

  const send = async (text: string, spoken = false) => {
    if (!sessionId) return
    setSelected(null)
    setMessages((list) => [...list, { role: 'user', text, spoken }, { role: 'guide', text: '', live: true }])
    setPending(true)
    const updateLive = (step: string) =>
      setMessages((list) => list.map((item) => (item.role === 'guide' && item.live ? { ...item, step } : item)))
    try {
      const turn = await api.chatStream(sessionId, text, {
        channel: spoken ? 'voice' : 'text',
        onStep: (step) => step.kind !== 'tool_done' && updateLive(stepLabel(step)),
      })
      setMessages((list) =>
        list.map((item) => (item.role === 'guide' && item.live ? { role: 'guide', text: turn.reply, spoken } : item)),
      )
      if (spoken) say(turn.spoken ?? turn.reply, VOICE_LANG)
    } catch (reason) {
      setMessages((list) => [
        ...list.filter((item) => !(item.role === 'guide' && item.live)),
        { role: 'note', text: `The Guide could not answer: ${String(reason)}` },
      ])
    } finally {
      setPending(false)
    }
  }

  const listen = async () => {
    if (listening) return
    setListening(true)
    try {
      const heard = await hearOnce(VOICE_LANG)
      setListening(false)
      if (heard.trim()) await send(heard.trim(), true)
    } catch (reason) {
      setListening(false)
      setMessages((list) => [...list, { role: 'note', text: `Could not hear you: ${String(reason)}` }])
    }
  }

  const ThemeIcon = THEME_ICON[theme.mode]

  return (
    <main className="screen">
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
          settings={DEFAULT_SETTINGS}
        />
      )}
      {!plan && (
        <div className="screen-status" role="status">
          {error ? <p>Could not open this building. {error}</p> : <p>Opening the building…</p>}
        </div>
      )}

      <header className="guide-line">
        <button type="button" className="round" onClick={onBack} aria-label="All buildings">
          <ChevronLeft size={20} strokeWidth={2.2} />
        </button>
        <div className="where">
          <h1>{plan?.building.name ?? 'Building'}</h1>
          {plan && (
            <p>
              {stacked
                ? 'All floors · tap one to step in'
                : `${current?.name ?? ''} · ${rooms} ${rooms === 1 ? 'room' : 'rooms'}`}
            </p>
          )}
        </div>
      </header>

      {plan && (
        <div className="map-controls">
          {plan.floors.length > 1 && (
            <nav className="floor-tabs" aria-label="Floors">
              <button
                type="button"
                aria-pressed={stacked}
                aria-label="All floors"
                title="All floors"
                onClick={() => {
                  setStacked((value) => !value)
                  setSelected(null)
                }}
              >
                <Layers size={18} strokeWidth={2} />
              </button>
              {[...plan.floors.keys()].reverse().map((index) => (
                <button
                  key={index}
                  type="button"
                  aria-pressed={!stacked && index === floor}
                  aria-label={plan.floors[index].name}
                  onClick={() => {
                    setFloor(index)
                    setStacked(false)
                    setSelected(null)
                  }}
                >
                  {floorTab(plan.floors[index].level)}
                </button>
              ))}
            </nav>
          )}
          <button type="button" className="round" onClick={() => setFitKey((key) => key + 1)} aria-label="Show it all" title="Show it all">
            <Scan size={19} strokeWidth={2} />
          </button>
          <button type="button" className="round" onClick={theme.cycle} aria-label={THEME_LABEL[theme.mode]} title={THEME_LABEL[theme.mode]}>
            <ThemeIcon size={19} strokeWidth={2} />
          </button>
        </div>
      )}

      <Conversation
        messages={messages}
        pending={pending}
        listening={listening}
        canListen={voiceSupported()}
        info={info}
        suggestions={suggestions}
        onSend={(text) => void send(text)}
        onListen={() => void listen()}
        onCloseInfo={() => setSelected(null)}
        onClear={() => setMessages([])}
      />
    </main>
  )
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
