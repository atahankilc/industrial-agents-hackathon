// The Guide, voice first: no chat thread. Captions say what is happening right now (you, live, while you speak;
// the Guide's work trail while it works — one line per lookup, from the streamed tool steps; its answer, like
// subtitles, with the trail folded into one line above it), with the Core below as the main control.
// Before the first question: a one-line greeting and a few things you can say. Typing is the fallback (keyboard
// button). A tapped room or object shows its card in the same place.
// The Edit mode talks to the Builder through the same card (`persona`): its own name, greeting and chips, and
// `card` (the selection's inspector, or the Builder's proposal) in the place of the room card.

import { Accessibility, ArrowUp, Bath, Check, ChevronDown, CircleHelp, DoorOpen, Keyboard, Layers, Navigation, PencilLine, RotateCcw, UtensilsCrossed, X } from 'lucide-react'
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode, type RefObject } from 'react'
import type { Step } from '../ui/guideSteps'
import type { VoiceState } from '../voice/useVoice'
import { Core } from './Core'

export type Message =
  | { role: 'user'; text: string; spoken?: boolean }
  | { role: 'guide'; text: string; live?: boolean; steps?: Step[]; spoken?: boolean; /** this answer drew a route */ route?: boolean }
  | { role: 'note'; text: string }

export type Suggestion = { label: string; prompt: string; icon: 'toilet' | 'exit' | 'access' | 'food' | 'floor' | 'help' | 'edit' }

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
  /** the answer's route is on screen as the next-move card: its numbered steps leave the caption */
  route: boolean
  /** `tapped`: a chip or the room card's Directions button, not typed — the reply is read aloud */
  onSend: (text: string, tapped?: boolean) => void
  onCloseInfo: () => void
  onClear: () => void
  persona?: Persona
  /** shown in the room card's place (and over it) */
  card?: ReactNode
}

const ICONS = { toilet: Bath, exit: DoorOpen, access: Accessibility, food: UtensilsCrossed, floor: Layers, help: CircleHelp, edit: PencilLine }

export function Guide({ messages, pending, voice, info, suggestions, route, onSend, onCloseInfo, onClear, persona = GUIDE, card }: Props) {
  const [typing, setTyping] = useState(!voice.supported)
  const [draft, setDraft] = useState('')
  // the answer that is opened, by its place in the list: a new message closes it again
  const [openAt, setOpenAt] = useState(-1)
  const expanded = openAt === messages.length
  const setExpanded = (toggle: (open: boolean) => boolean) => setOpenAt(toggle(expanded) ? messages.length : -1)
  const input = useRef<HTMLInputElement>(null)
  // a long reply is cut to a few lines and fades out; a short one is shown whole, without the fade
  const reply = useRef<HTMLDivElement>(null)
  const [clipped, setClipped] = useState(false)
  useLayoutEffect(() => {
    const box = reply.current
    const next = !!box && box.scrollHeight > box.clientHeight + 1
    setClipped(next)
  }, [messages, route, expanded])

  useEffect(() => {
    if (typing) input.current?.focus()
  }, [typing])

  const submit = (text: string, tapped = false) => {
    const value = text.trim()
    if (!value || pending) return
    onSend(value, tapped)
    setDraft('')
    if (voice.supported) setTyping(false)
  }

  // the latest exchange starts at the last thing the user said
  const lastUser = messages.map((message) => message.role).lastIndexOf('user')
  const question = lastUser >= 0 ? (messages[lastUser] as { text: string }).text : null
  const answer = lastUser >= 0 ? messages.slice(lastUser + 1).at(-1) : messages.at(-1)
  const fresh = messages.length === 0

  let caption
  if (voice.state === 'listening') {
    caption = (
      <div className="caption big">
        <p className="who live">{voice.hearing === false ? 'Mic starting' : 'You · live'}</p>
        <p className="said">{voice.interim ? lastWordSoft(voice.interim) : <em>{voice.hearing === false ? 'One moment…' : 'Listening… go ahead'}</em>}</p>
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
        <p className="who">{persona.who}</p>
        <p className="said">{persona.greeting}</p>
      </div>
    )
  } else {
    const working = answer?.role === 'guide' && answer.live
    caption = (
      <div className="caption">
        {question && <p className="asked">{question}</p>}
        {answer?.role === 'note' && <p className="said warn">{answer.text}</p>}
        {working && (
          <>
            <p className="who">{persona.who} · working</p>
            <Trail steps={answer.steps ?? []} live />
          </>
        )}
        {answer?.role === 'guide' && !answer.live && (
          <>
            {!!answer.steps?.length && <FoldedTrail steps={answer.steps} />}
            <p className={`who ${voice.state === 'speaking' ? 'speaking' : ''}`}>{voice.state === 'speaking' ? `${persona.who} · speaking` : persona.who}</p>
            <div
              ref={reply}
              className={`said reply ${expanded ? 'open' : ''} ${clipped ? 'clipped' : ''}`}
              role="button"
              tabIndex={0}
              aria-expanded={expanded}
              onClick={() => setExpanded((open) => !open)}
              onKeyDown={(event) => (event.key === 'Enter' || event.key === ' ') && setExpanded((open) => !open)}
            >
              {lines(answer.text, route && !!answer.route)}
            </div>
          </>
        )}
      </div>
    )
  }

  return (
    <section className="guide" aria-label={persona.who}>
      {voice.error && voice.state !== 'listening' && <p className="voice-error">{voice.error}</p>}
      {caption}

      {fresh && !info && !card && !typing && voice.state !== 'listening' && (
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

      {typing && (
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
            placeholder={persona.placeholder}
            aria-label={persona.placeholder}
            enterKeyHint="send"
          />
          <button type="submit" className="send" disabled={pending || !draft.trim()} aria-label="Send">
            <ArrowUp size={18} strokeWidth={2.4} />
          </button>
        </form>
      )}

      {voice.supported && (
        <div className="dock">
          <button type="button" className="hud-side" aria-pressed={typing} onClick={() => setTyping((open) => !open)} aria-label={typing ? 'Back to voice' : 'Type instead'} title={typing ? 'Back to voice' : 'Type instead'}>
            {typing ? <X size={20} /> : <Keyboard size={20} />}
          </button>
          <Core state={voice.state} level={voice.level} busy={pending} onListen={voice.listen} onFinish={voice.finish} onStop={voice.stop} />
          <button type="button" className="hud-side" onClick={onClear} disabled={fresh || pending} aria-label="Start over" title="Start over">
            <RotateCcw size={19} />
          </button>
        </div>
      )}
      {voice.supported && <p className="core-hint">{hint(voice.state, pending, voice.bargeIn, voice.hearing)}</p>}
    </section>
  )
}

/** What the Guide is doing: one line per lookup, the running one with a spinner and its seconds. */
function Trail({ steps, live = false }: { steps: Step[]; live?: boolean }) {
  return (
    <ol className="trail" aria-live={live ? 'polite' : undefined}>
      {steps.length === 0 && live && (
        <li className="running">
          <span className="mark" aria-hidden="true" />
          <span>Looking at the building</span>
          <Elapsed />
        </li>
      )}
      {steps.map((step, index) => (
        <li key={step.key} className={step.state}>
          <span className="mark" aria-hidden="true">
            {step.state === 'done' && <Check size={10} strokeWidth={3.2} />}
            {step.state === 'failed' && <X size={10} strokeWidth={3.2} />}
          </span>
          <span>{step.label}</span>
          {live && index === steps.length - 1 && step.state === 'running' && <Elapsed />}
          {step.state === 'failed' && <small>no result</small>}
        </li>
      ))}
    </ol>
  )
}

/** After the answer: the trail folds into one line ("✓ 3 checks") that opens it again. */
function FoldedTrail({ steps }: { steps: Step[] }) {
  const [open, setOpen] = useState(false)
  const failed = steps.filter((step) => step.state === 'failed').length
  return (
    <div className="trail-fold">
      <button type="button" onClick={() => setOpen((value) => !value)} aria-expanded={open}>
        <Check size={12} strokeWidth={2.6} aria-hidden="true" />
        {steps.length} {steps.length === 1 ? 'check' : 'checks'}
        {failed > 0 && ` · ${failed} without result`}
        <ChevronDown size={13} className={open ? 'open' : ''} aria-hidden="true" />
      </button>
      {open && <Trail steps={steps} />}
    </div>
  )
}

/** Seconds on the running step, so a slow lookup reads as progress, not as a hang. */
function Elapsed() {
  const [seconds, setSeconds] = useState(0)
  useEffect(() => {
    const timer = setInterval(() => setSeconds((value) => value + 1), 1000)
    return () => clearInterval(timer)
  }, [])
  return <small>{seconds > 0 ? `${seconds}s` : ''}</small>
}

const hint = (state: VoiceState, pending: boolean, bargeIn = false, hearing = true) =>
  state === 'listening' ? (hearing ? 'Release or tap to send' : 'Starting the mic…')
    : state === 'speaking' ? (bargeIn ? 'Talk to interrupt · tap to stop' : 'Tap to stop')
    : pending || state === 'thinking' ? 'Working' : 'Tap or hold to talk'

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
 * route on screen as the next-move card, the numbered steps are there instead (a lead-in's ":" becomes "."). */
function lines(text: string, route: boolean) {
  const all = text.replace(/\*\*(.+?)\*\*/g, '$1').split(/\n+/).map((line) => line.trim()).filter(Boolean)
  const prose = route ? all.filter((line) => !/^\d+[.)]\s/.test(line)) : all
  const shown = prose.length ? prose : all
  return shown.map((line, index) => <p key={index}>{route && index === shown.length - 1 ? line.replace(/:$/, '.') : line}</p>)
}
