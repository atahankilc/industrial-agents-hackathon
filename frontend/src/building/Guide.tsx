// The Guide, voice first: no chat thread. Captions say what is happening right now (you, live, while you speak;
// the Guide's work trail while it works — one line per lookup, from the streamed tool steps; its answer, like
// subtitles above the ball, with the trail folded into one line above it), with the dock below. No panel: the
// caption is a glass bubble that is there only when it has something to say, and the dock floats over the map.
// The dock is three places: the main way to ask in the middle, the other way on the left, the options on the right.
// Talking first (default): the Core (the ball) in the middle, a keyboard button on the left that brings the message
// field into the middle, focused (Escape, or leaving it empty, brings the ball back). Typing first: the field in the
// middle and a small ball on the left. The options set which comes first, how the ball listens (tap, the default,
// or hold to talk) and turn the spoken replies off (text only); all remembered on this device.
// While a route is followed, `routeBar` (its one-line caption and button) sits over the dock, and `quiet` keeps the
// last answer's bubble away until there is something new to say.
// Before the first question: a one-line greeting and a few things you can say. A tapped room or object shows its
// card in the same place.
// The Edit mode talks to the Builder through the same card (`persona`): its own name, greeting and chips, and
// `card` (the selection's inspector, or the Builder's proposal) in the place of the room card.

import { Accessibility, ArrowUp, ArrowUpDown, Bath, Check, ChevronDown, ChevronLeft, ChevronRight, CircleHelp, DoorOpen, Keyboard, Layers, MapPin, Navigation, PencilLine, RotateCcw, SlidersHorizontal, UtensilsCrossed, X } from 'lucide-react'
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode, type RefObject } from 'react'
import type { Step } from '../ui/guideSteps'
import type { VoiceState } from '../voice/useVoice'
import { Core } from './Core'

export type Message =
  | { role: 'user'; text: string; spoken?: boolean }
  | { role: 'guide'; text: string; live?: boolean; steps?: Step[]; spoken?: boolean; /** this answer drew a route */ route?: boolean }
  | { role: 'note'; text: string }

export type Suggestion = { label: string; prompt: string; icon: 'toilet' | 'exit' | 'lift' | 'access' | 'food' | 'floor' | 'here' | 'help' | 'edit' }

/** who the card talks for: the Guide (default) or the Edit mode's Builder */
export type Persona = { who: string; greeting: ReactNode; placeholder: string }
const GUIDE: Persona = {
  who: 'Guide',
  greeting: <>Hi, I know this building. <em>Where do you need to go?</em></>,
  placeholder: 'Ask the building',
}

export type InfoCard = { title: string; meta: string; detail?: string; directions?: string }

export type VoiceView = {
  state: VoiceState
  interim: string
  error: string | null
  level: RefObject<number>
  supported: boolean
  /** the user can talk over the reply being spoken (useVoice barge-in) */
  bargeIn?: boolean
  /** while listening: the microphone really captures (until then the caption says it is starting) */
  hearing?: boolean
  /** the Guide answers aloud (useVoice `speaks`); the options menu turns it off */
  speaks?: boolean
  setSpeaks?: (on: boolean) => void
  /** push to talk (useVoice `holdToTalk`, default off: a tap listens): listen while the ball is held; the options switch it */
  holdToTalk?: boolean
  setHoldToTalk?: (on: boolean) => void
  hold?: () => void
  listen: () => void
  finish: () => void
  stop: () => void
}

type Props = {
  messages: Message[]
  pending: boolean
  voice: VoiceView
  info: InfoCard | null
  suggestions: Suggestion[]
  /** the answer's route is on screen in the route bar: its numbered steps leave the caption */
  route: boolean
  /** `tapped`: a chip or the room card's Directions button, not typed — the reply is read aloud */
  onSend: (text: string, tapped?: boolean) => void
  onCloseInfo: () => void
  onClear: () => void
  persona?: Persona
  /** shown in the room card's place (and over it) */
  card?: ReactNode
  /** the Guide's height in px whenever it changes (the plan keeps its buttons above it on a phone) */
  onHeight?: (px: number) => void
  /** the route being followed: its caption and button, right over the dock */
  routeBar?: ReactNode
  /** a step is being walked: the last answer's bubble stays away (it comes back while listening or answering) */
  quiet?: boolean
}

const ICONS = { toilet: Bath, exit: DoorOpen, lift: ArrowUpDown, access: Accessibility, food: UtensilsCrossed, floor: Layers, here: MapPin, help: CircleHelp, edit: PencilLine }

const FIRST_KEY = 'ttyb-guide-first'
type Way = 'talk' | 'type'

export function Guide({ messages, pending, voice, info, suggestions, route, onSend, onCloseInfo, onClear, persona = GUIDE, card, onHeight, routeBar, quiet = false }: Props) {
  // which way of asking sits in the middle of the dock: the user's choice, or typing for now (the keyboard button);
  // always typing without voice
  const [first, setFirst] = useState<Way>(() => readFirst())
  const [typingNow, setTypingNow] = useState(false)
  const center: Way = !voice.supported || first === 'type' || typingNow ? 'type' : 'talk'
  const chooseFirst = (way: Way) => {
    setFirst(way)
    setTypingNow(false)
    writeFirst(way)
  }
  const [options, setOptions] = useState(false)
  const [draft, setDraft] = useState('')
  // the answer that is opened, by its place in the list: a new message closes it again
  // earlier exchanges, one at a time (the arrows beside the question), by their place among the questions; held
  // for this length of the conversation only, so a new message goes back to the latest by itself
  const turns = messages.flatMap((message, index) => (message.role === 'user' ? [index] : []))
  const [viewing, setViewing] = useState({ at: -1, turn: 0 })
  const latest = turns.length - 1
  const turn = viewing.at === messages.length ? viewing.turn : latest
  const past = turn < latest
  const viewTurn = (next: number) => setViewing({ at: messages.length, turn: Math.max(0, Math.min(latest, next)) })
  const [openAt, setOpenAt] = useState('')
  const openKey = `${messages.length}:${turn}`
  const expanded = openAt === openKey
  const setExpanded = (toggle: (open: boolean) => boolean) => setOpenAt(toggle(expanded) ? openKey : '')
  const input = useRef<HTMLInputElement>(null)
  // a long reply is cut to a few lines and fades out; a short one is shown whole, without the fade
  const reply = useRef<HTMLDivElement>(null)
  const [clipped, setClipped] = useState(false)
  useLayoutEffect(() => {
    const box = reply.current
    const next = !!box && box.scrollHeight > box.clientHeight + 1
    setClipped(next)
  }, [messages, route, expanded, turn])

  const root = useRef<HTMLElement>(null)
  useEffect(() => {
    const element = root.current
    if (!element || !onHeight) return
    const watch = new ResizeObserver(() => onHeight(Math.round(element.offsetHeight)))
    watch.observe(element)
    return () => watch.disconnect()
  }, [onHeight])

  // the field comes into the middle focused
  useEffect(() => {
    if (typingNow) input.current?.focus()
  }, [typingNow])

  // the options menu closes on a tap anywhere else
  const optionsBox = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!options) return
    const close = (event: PointerEvent) => !optionsBox.current?.contains(event.target as Node) && setOptions(false)
    addEventListener('pointerdown', close)
    return () => removeEventListener('pointerdown', close)
  }, [options])

  const submit = (text: string, tapped = false) => {
    const value = text.trim()
    if (!value || pending) return
    onSend(value, tapped)
    setDraft('')
  }

  // the latest exchange starts at the last thing the user said
  // the exchange shown: the latest (or an earlier one) starts at what the user said and runs to the next question
  const asked = turns[turn] ?? -1
  const question = asked >= 0 ? (messages[asked] as { text: string }).text : null
  const answer = asked >= 0 ? messages.slice(asked + 1, turns[turn + 1] ?? messages.length).at(-1) : messages.at(-1)
  const history = turns.length > 1 ? { turn, count: turns.length, go: viewTurn } : undefined
  const fresh = messages.length === 0

  let caption
  if (voice.state === 'listening') {
    caption = (
      <div className="caption big">
        <p className="who live">{voice.hearing === false ? 'Mic starting' : 'You · live'}</p>
        <p className="said">{voice.interim ? lastWordSoft(voice.interim) : <em>{voice.hearing === false ? 'One moment…' : voice.holdToTalk ? 'Listening… let go to send' : 'Listening… go ahead'}</em>}</p>
      </div>
    )
  } else if (card) {
    caption = card
  } else if (info) {
    caption = (
      <article className="place-card">
        <header>
          <div>
            <p className="who">{info.meta}</p>
            <h2>{info.title}</h2>
            {info.detail && <p className="detail">{info.detail}</p>}
          </div>
          <button type="button" className="hud-icon" onClick={onCloseInfo} aria-label="Close">
            <X size={16} />
          </button>
        </header>
        {info.directions && (
          <button type="button" className="hud-primary" onClick={() => submit(info.directions!, true)}>
            <Navigation size={17} strokeWidth={2.2} aria-hidden="true" />
            Directions
          </button>
        )}
      </article>
    )
  } else if (fresh) {
    caption = (
      <div className="caption big">
        <p className="said">{persona.greeting}</p>
      </div>
    )
  } else {
    const working = answer?.role === 'guide' && answer.live
    caption = (
      <div className="caption">
        {question && <Exchange key={turn} question={question} steps={answer?.role === 'guide' && !answer.live ? answer.steps ?? [] : []} history={history} />}
        {answer?.role === 'note' && <p className="said warn">{answer.text}</p>}
        {working && <Thinking steps={answer.steps ?? []} />}
        {answer?.role === 'guide' && !answer.live && (
          <>
            {voice.state === 'speaking' && !past && <p className="who speaking">Speaking</p>}
            <div
              ref={reply}
              className={`said reply ${expanded ? 'open' : ''} ${clipped ? 'clipped' : ''}`}
              role="button"
              tabIndex={0}
              aria-expanded={expanded}
              onClick={() => setExpanded((open) => !open)}
              onKeyDown={(event) => (event.key === 'Enter' || event.key === ' ') && setExpanded((open) => !open)}
            >
              {lines(answer.text, route && !past && !!answer.route)}
            </div>
          </>
        )}
      </div>
    )
  }

  // talking from the small ball gives the middle back to the ball
  const listen = () => {
    setTypingNow(false)
    voice.listen()
  }
  const hold = voice.hold && (() => {
    setTypingNow(false)
    voice.hold!()
  })
  const ball = voice.supported && (
    <Core state={voice.state} level={voice.level} busy={pending} hold={voice.holdToTalk} onHold={hold} onListen={listen} onFinish={voice.finish} onStop={voice.stop} />
  )

  return (
    <section ref={root} className={`guide ${center}`} aria-label={persona.who}>
      {voice.error && voice.state !== 'listening' && <p className="voice-error">{voice.error}</p>}
      {caption && !(quiet && !pending && voice.state !== 'listening' && !info && !card) && <div className={`guide-bubble${past && !info && !card && voice.state !== 'listening' ? ' past' : ''}`}>{caption}</div>}

      {fresh && !info && !card && voice.state !== 'listening' && (
        <ul className="intents" aria-label="Things you can ask">
          {suggestions.slice(0, 3).map((item) => {
            const Icon = ICONS[item.icon]
            return (
              <li key={item.label}>
                <button type="button" onClick={() => submit(item.prompt, true)}>
                  <Icon size={15} strokeWidth={2} aria-hidden="true" />
                  {item.label}
                </button>
              </li>
            )
          })}
        </ul>
      )}

      {routeBar}
      <div className="dock">
        <div className="dock-side">
          {center === 'talk' ? (
            <button type="button" className="hud-side" onClick={() => setTypingNow(true)} aria-label="Type instead" title="Type instead">
              <Keyboard size={20} />
            </button>
          ) : (
            ball
          )}
        </div>
        <div className="dock-center">
          {center === 'talk' ? (
            ball
          ) : (
            <form
              className="type-bar"
              onSubmit={(event) => {
                event.preventDefault()
                submit(draft)
              }}
            >
              <input
                ref={input}
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={(event) => event.key === 'Escape' && setTypingNow(false)}
                // leaving it empty gives the middle back to the ball, unless the focus stays in the dock (options, send)
                onBlur={(event) => !draft.trim() && !event.currentTarget.closest('.dock')?.contains(event.relatedTarget) && setTypingNow(false)}
                placeholder={persona.placeholder}
                aria-label={persona.placeholder}
                enterKeyHint="send"
              />
              <button type="submit" className="send" disabled={pending || !draft.trim()} aria-label="Send">
                <ArrowUp size={18} strokeWidth={2.4} />
              </button>
            </form>
          )}
        </div>
        <div className="dock-side dock-options" ref={optionsBox}>
          <button type="button" className="hud-side" aria-expanded={options} aria-haspopup="true" onClick={() => setOptions((open) => !open)} aria-label="Options" title="Options">
            <SlidersHorizontal size={19} />
          </button>
          {options && (
            <div className="hud-pop dock-pop" role="group" aria-label="Options">
              {voice.supported && (
                <div className="dock-row">
                  <span>Ask by</span>
                  <div className="dock-seg" role="radiogroup" aria-label="Ask by">
                    {(['talk', 'type'] as const).map((way) => (
                      <button key={way} type="button" role="radio" aria-checked={first === way} onClick={() => chooseFirst(way)}>
                        {way === 'talk' ? 'Voice' : 'Text'}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {voice.setHoldToTalk && (
                <div className="dock-row">
                  <span>
                    Talk by
                    <small>{voice.holdToTalk ? 'While you hold the ball' : 'Until you pause'}</small>
                  </span>
                  <div className="dock-seg" role="radiogroup" aria-label="Talk by">
                    {([true, false] as const).map((on) => (
                      <button key={String(on)} type="button" role="radio" aria-checked={(voice.holdToTalk ?? false) === on} onClick={() => voice.setHoldToTalk!(on)}>
                        {on ? 'Hold' : 'Tap'}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {voice.setSpeaks && (
                <Toggle label="Spoken replies" detail="Answers are read aloud" on={voice.speaks ?? true} onChange={voice.setSpeaks} />
              )}
              <button
                type="button"
                className="dock-clear"
                disabled={fresh || pending}
                onClick={() => {
                  setOptions(false)
                  onClear()
                }}
              >
                <RotateCcw size={16} aria-hidden="true" />
                Start over
              </button>
            </div>
          )}
        </div>
      </div>
    </section>
  )
}

/** One on/off row of the options menu. */
function Toggle({ label, detail, on, onChange }: { label: string; detail: string; on: boolean; onChange: (on: boolean) => void }) {
  return (
    <button type="button" role="switch" aria-checked={on} className="dock-toggle" onClick={() => onChange(!on)}>
      <span>
        {label}
        <small>{detail}</small>
      </span>
      <i className={on ? 'on' : ''} aria-hidden="true" />
    </button>
  )
}

function readFirst(): Way {
  try {
    return localStorage.getItem(FIRST_KEY) === 'type' ? 'type' : 'talk'
  } catch {
    return 'talk'
  }
}
function writeFirst(way: Way) {
  try {
    localStorage.setItem(FIRST_KEY, way)
  } catch {
    // storage unavailable: the choice just isn't remembered
  }
}

/** While the Guide works: what it is doing right now, in one shimmering line, and a dot per lookup so far (the
 * running one pulses). Lookups that found nothing stay quiet — the answer says what matters. */
function Thinking({ steps }: { steps: Step[] }) {
  const current = steps.findLast((step) => step.state === 'running') ?? steps.at(-1)
  return (
    <div className="work" aria-live="polite">
      <p className="work-now" key={current?.key ?? -1}>
        <span>{current ? current.label : 'Thinking'}</span>
      </p>
      <div className="work-meta" aria-hidden="true">
        <ol className="work-dots">
          {steps.map((step) => (
            <li key={step.key} className={step.state} />
          ))}
        </ol>
        <Elapsed />
      </div>
    </div>
  )
}

type History = { turn: number; count: number; go: (turn: number) => void }

/** The question, and beside it the arrows through earlier exchanges ("‹ 2/5 ›") and, after an answer, a quiet
 * "3 steps" that opens what the Guide looked up. */
function Exchange({ question, steps, history }: { question: string; steps: Step[]; history?: History }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <div className="exchange">
        <p className="asked">{question}</p>
        {steps.length > 0 && (
          <button type="button" className="steps-toggle" onClick={() => setOpen((value) => !value)} aria-expanded={open}>
            {steps.length} {steps.length === 1 ? 'step' : 'steps'}
            <ChevronDown size={13} className={open ? 'open' : ''} aria-hidden="true" />
          </button>
        )}
        {history && (
          <span className="history">
            <button type="button" disabled={history.turn === 0} onClick={() => history.go(history.turn - 1)} aria-label="Earlier answer" title="Earlier answer">
              <ChevronLeft size={15} />
            </button>
            <span aria-live="polite">{history.turn + 1}/{history.count}</span>
            <button type="button" disabled={history.turn === history.count - 1} onClick={() => history.go(history.turn + 1)} aria-label="Later answer" title="Later answer">
              <ChevronRight size={15} />
            </button>
          </span>
        )}
      </div>
      {open && (
        <ol className="trail">
          {steps.map((step) => (
            <li key={step.key} className={step.state}>
              <span className="mark" aria-hidden="true">{step.state === 'done' && <Check size={9} strokeWidth={3.4} />}</span>
              <span>{step.label}</span>
              {step.state === 'failed' && <small>no match</small>}
            </li>
          ))}
        </ol>
      )}
    </>
  )
}

/** Seconds since the Guide started, from the third on, so a slow lookup reads as progress, not as a hang. */
function Elapsed() {
  const [seconds, setSeconds] = useState(0)
  useEffect(() => {
    const timer = setInterval(() => setSeconds((value) => value + 1), 1000)
    return () => clearInterval(timer)
  }, [])
  return <small className="elapsed">{seconds >= 3 ? `${seconds}s` : ''}</small>
}

/** The words so far, the last one still forming. */
function lastWordSoft(text: string) {
  const cut = text.lastIndexOf(' ')
  if (cut < 0) return <em>{text}</em>
  return (
    <>
      {text.slice(0, cut + 1)}
      <em>{text.slice(cut + 1)}</em>
    </>
  )
}

/** Guide replies are short prose, sometimes with numbered steps: drop markdown emphasis, keep the lines. With the
 * route on screen in the route bar, the numbered steps are there instead (a lead-in's ":" becomes "."). */
function lines(text: string, route: boolean) {
  const all = text.replace(/\*\*(.+?)\*\*/g, '$1').split(/\n+/).map((line) => line.trim()).filter(Boolean)
  const prose = route ? all.filter((line) => !/^\d+[.)]\s/.test(line)) : all
  const shown = prose.length ? prose : all
  return shown.map((line, index) => <p key={index}>{route && index === shown.length - 1 ? line.replace(/:$/, '.') : line}</p>)
}
