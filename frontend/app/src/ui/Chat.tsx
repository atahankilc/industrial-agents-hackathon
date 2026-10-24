// Conversation panel: the Guide's replies (light markdown: paragraphs, numbered/bulleted lines, **bold**), a live
// checklist of what the Guide is doing while it works (POST /chat/stream steps), route and change cards, follow-up
// chips, a voice mode with the orb (browser speech, voice/useVoice.ts) and the camera walk mode (CameraGuide).

import { useCallback, useEffect, useRef, useState, type FormEvent, type ReactNode, type RefObject } from 'react'
import { createPortal } from 'react-dom'
import type { ChatReply } from '../api'
import { LANGUAGES, useVoice, voiceSupported, type VoiceState } from '../voice/useVoice'
import { CameraGuide } from './CameraGuide'
import { AppliedNote, ChangeCard, RouteCard, type RouteCardData } from './cards/Cards'
import type { Step } from './guideSteps'
import { VoiceOrb } from './VoiceOrb'
import './chat.css'

export type Message = {
  role: 'user' | 'guide' | 'note' | 'applied'
  text: string
  steps?: Step[]
  route?: RouteCardData
  followups?: string[]
  spoken?: string | null
  photo?: boolean
  live?: boolean // the reply is still being worked out
}

export type SendOptions = { channel?: 'text' | 'voice'; photo?: string }

const SUGGESTIONS = [
  'Where is the nearest printer?',
  'I use a wheelchair.',
  'Take me from the main lobby to a meeting room.',
  'The lift is out of order.',
]

function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, index) =>
    part.startsWith('**') && part.endsWith('**') ? <strong key={index}>{part.slice(2, -2)}</strong> : part,
  )
}

const LIST_LINE = /^\s*(\d+[.)]|[-•])\s/
// Tool texts carry ids like "Main lobby [proc-…-F0-S012]"; people don't need them on screen.
const RAW_ID = /\s*\[[A-Za-z0-9]+(?:-[A-Za-z0-9]+){2,}\]/g

function Rich({ text }: { text: string }) {
  const groups: { list: 'ol' | 'ul' | null; lines: string[] }[] = []
  for (const raw of text.replace(RAW_ID, '').split('\n')) {
    const line = raw.trimEnd()
    const marker = line.match(LIST_LINE)
    const list = marker ? (/\d/.test(marker[1]) ? 'ol' : 'ul') : null
    const last = groups[groups.length - 1]
    if (!line.trim()) {
      groups.push({ list: null, lines: [] })
    } else if (last && last.list === list && (list || last.lines.length)) {
      last.lines.push(line)
    } else {
      groups.push({ list, lines: [line] })
    }
  }
  return (
    <>
      {groups
        .filter((group) => group.lines.length)
        .map((group, index) => {
          if (group.list) {
            const List = group.list
            return (
              <List key={index}>
                {group.lines.map((line, item) => <li key={item}>{inline(line.replace(LIST_LINE, ''))}</li>)}
              </List>
            )
          }
          return (
            <p key={index}>
              {group.lines.map((line, item) => (
                <span key={item}>{inline(line)}{item < group.lines.length - 1 && <br />}</span>
              ))}
            </p>
          )
        })}
    </>
  )
}

function Elapsed() {
  const [seconds, setSeconds] = useState(0)
  useEffect(() => {
    const started = performance.now()
    const timer = setInterval(() => setSeconds(Math.floor((performance.now() - started) / 1000)), 500)
    return () => clearInterval(timer)
  }, [])
  return seconds >= 2 ? <span className="elapsed">{seconds}s</span> : null
}

/** The live checklist while a turn runs; folded into one quiet line once the reply is in. */
function Steps({ steps, live }: { steps: Step[]; live: boolean }) {
  const [open, setOpen] = useState(false)
  if (!live && !steps.length) return null
  if (live) {
    return (
      <div className="steps live" aria-label="The guide is working">
        {steps.length === 0 && (
          <div className="step running"><span className="dots"><i /><i /><i /></span><span>Thinking</span><Elapsed /></div>
        )}
        {steps.map((step, index) => (
          <div key={step.key} className={`step ${step.state}`}>
            <span className="tick" aria-hidden="true" />
            <span>{step.label}</span>
            {index === steps.length - 1 && step.state === 'running' && <Elapsed />}
          </div>
        ))}
      </div>
    )
  }
  return (
    <div className="steps">
      <button type="button" className="steps-toggle" onClick={() => setOpen((on) => !on)} aria-expanded={open}>
        Checked {steps.length} {steps.length === 1 ? 'thing' : 'things'} in the building
        <svg viewBox="0 0 10 6" width="8" height="6" aria-hidden="true"><path d={open ? 'M1 5l4-4 4 4' : 'M1 1l4 4 4-4'} fill="none" stroke="currentColor" strokeWidth="1.2" /></svg>
      </button>
      {open && steps.map((step) => (
        <div key={step.key} className={`step ${step.state}`}><span className="tick" aria-hidden="true" /><span>{step.label}</span></div>
      ))}
    </div>
  )
}

/** Voice mode: one big orb, the words it heard, what the Guide is doing, then its reply as captions. */
function VoiceStage({ state, level, error, heard, reply, onOrb, onWalk, onShowRoute }: {
  state: VoiceState
  level: RefObject<number>
  error: string | null
  heard: string
  reply: Message | null
  onOrb: () => void
  onWalk: (route: RouteCardData) => void
  onShowRoute: (route: RouteCardData) => void
}) {
  const showReply = reply && !reply.live && (state === 'speaking' || state === 'off')
  return (
    <div className={`voice-stage ${state}`}>
      <div className="stage-orb">
        <VoiceOrb state={state} level={level} size={208} onClick={onOrb} label={VOICE_STATUS[state]} />
      </div>
      <p className={`voice-status${error ? ' error' : ''}`} aria-live="assertive">{error ?? VOICE_STATUS[state]}</p>
      <p className={`voice-heard${heard ? '' : ' empty'}`}>{heard || (state === 'listening' ? 'Say something like “take me to the nearest toilet”' : '\u00a0')}</p>
      <div className="stage-feed" aria-live="polite">
        {reply?.live && <Steps steps={reply.steps ?? []} live />}
        {showReply && (
          <div className="caption">
            <Rich text={reply.spoken ?? reply.text} />
            {reply.route && <RouteCard route={reply.route} onShow={() => onShowRoute(reply.route!)} onWalk={() => onWalk(reply.route!)} />}
          </div>
        )}
      </div>
    </div>
  )
}

const VOICE_STATUS: Record<VoiceState, string> = { off: 'Tap the orb to talk', listening: 'Listening… tap when you are done', thinking: 'Checking the building…', speaking: 'Speaking — tap to interrupt' }

type Props = {
  messages: Message[]
  pending: boolean
  disabled: boolean
  profile: string | null
  pendingChanges: { id: string; summary: string }[]
  onSend: (text: string, options?: SendOptions) => Promise<ChatReply | null>
  onShowRoute: (route: RouteCardData) => void
}

export function Chat({ messages, pending, disabled, profile, pendingChanges, onSend, onShowRoute }: Props) {
  const [draft, setDraft] = useState('')
  const [voiceMode, setVoiceMode] = useState(false)
  const [walking, setWalking] = useState<RouteCardData | null>(null)
  const log = useRef<HTMLDivElement>(null)
  const input = useRef<HTMLTextAreaElement>(null)
  const canVoice = voiceSupported()

  const latestRoute = [...messages].reverse().find((message) => message.route)?.route ?? null

  const voice = useVoice({
    onUtterance: useCallback(
      (text: string) => {
        if (pending || disabled) return false
        void onSend(text, { channel: 'voice' }).then((reply) => {
          if (!reply) voice.idle()
          else voice.speak(reply.spoken ?? reply.reply)
        })
        return true
      },
      // voice is stable enough here: speak/idle are memoised inside the hook
      // eslint-disable-next-line react-hooks/exhaustive-deps
      [pending, disabled, onSend],
    ),
  })

  // The camera view follows the newest route (a re-route while walking replaces it).
  useEffect(() => {
    if (walking && latestRoute && latestRoute.key !== walking.key) setWalking(latestRoute)
  }, [latestRoute, walking])

  useEffect(() => {
    log.current?.scrollTo({ top: log.current.scrollHeight, behavior: 'smooth' })
  }, [messages, pending, pendingChanges.length])

  // Grow the composer with its text, up to the CSS max-height.
  useEffect(() => {
    const element = input.current
    if (!element) return
    element.style.height = 'auto'
    element.style.height = `${element.scrollHeight}px`
  }, [draft])

  const send = (event?: FormEvent) => {
    event?.preventDefault()
    const text = draft.trim()
    if (!text || pending || disabled) return
    void onSend(text)
    setDraft('')
  }

  const pick = (text: string) => {
    if (!pending && !disabled) void onSend(text)
  }

  const toggleVoice = () => {
    if (voiceMode) {
      voice.stop()
      setVoiceMode(false)
    } else {
      setVoiceMode(true)
      voice.listen()
    }
  }

  const tapOrb = () => {
    if (voice.state === 'listening') voice.finish()
    else if (voice.state === 'speaking' || voice.state === 'off') voice.listen()
  }

  const lastGuide = messages.findLastIndex((message) => message.role === 'guide')
  const lastGuideMessage = lastGuide >= 0 ? messages[lastGuide] : null
  const lastUser = [...messages].reverse().find((message) => message.role === 'user')
  const displayState = pending && voice.state !== 'listening' ? 'thinking' : voice.state

  return (
    <section className="chat" aria-label="Conversation with the building guide">
      <header className="chat-head">
        <span className="chat-title">Guide</span>
        {profile && <span className="profile-chip" title="Your routing profile">{profile}</span>}
      </header>

      {voiceMode ? (
        <VoiceStage
          state={displayState}
          level={voice.level}
          error={voice.error}
          heard={voice.interim || (voice.state === 'listening' ? '' : lastUser?.text ?? '')}
          reply={lastGuideMessage}
          onOrb={tapOrb}
          onWalk={setWalking}
          onShowRoute={onShowRoute}
        />
      ) : (
      <div className="log" ref={log} aria-live="polite">
        {messages.length === 0 && (
          <div className="empty">
            <div className="empty-orb">
              <VoiceOrb state="off" level={voice.level} size={168} disabled={disabled} onClick={toggleVoice} label="Talk to the building" />
              <span className="muted">{canVoice ? 'Tap to talk' : 'Voice needs Chrome, Edge or Safari'}</span>
            </div>
            <p className="lead">Ask the building.</p>
            <p className="muted">Find things, get step-by-step directions, report what is broken — by text, voice or camera.</p>
            <div className="suggestions">
              {SUGGESTIONS.map((text) => (
                <button key={text} type="button" disabled={disabled} onClick={() => pick(text)}>
                  {text}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((message, index) => {
          if (message.role === 'applied') return <AppliedNote key={index} text={message.text} />
          if (message.role !== 'guide') {
            return (
              <div key={index} className={`message ${message.role}`}>
                <p>{message.photo && <span className="photo-tag">photo · </span>}{message.text}</p>
              </div>
            )
          }
          return (
            <div key={index} className={`message guide${message.live ? ' live' : ''}`}>
              <Steps steps={message.steps ?? []} live={Boolean(message.live)} />
              {message.text && <Rich text={message.text} />}
              {message.route && (
                <RouteCard route={message.route} onShow={() => onShowRoute(message.route!)} onWalk={() => setWalking(message.route!)} />
              )}
              {index === lastGuide && !pending && message.followups && message.followups.length > 0 && (
                <div className="followups">
                  {message.followups.map((text) => (
                    <button key={text} type="button" disabled={disabled} onClick={() => pick(text)}>
                      {text}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )
        })}
        {!pending && pendingChanges.map((change) => (
          <ChangeCard
            key={change.id}
            summary={change.summary}
            busy={pending || disabled}
            onApply={() => void onSend(`Yes, apply it: ${change.summary}`)}
            onDiscard={() => void onSend(`No, don't apply that change (${change.summary}).`)}
          />
        ))}
      </div>
      )}

      {voiceMode ? (
        <div className={`voice-dock ${voice.state}`}>
          <div className="voice-controls">
            <div className="segmented" role="radiogroup" aria-label="Voice language">
              {LANGUAGES.map((language) => (
                <button key={language.code} type="button" role="radio" aria-checked={voice.lang === language.code} className={voice.lang === language.code ? 'on' : ''} onClick={() => voice.setLang(language.code)}>
                  {language.label}
                </button>
              ))}
            </div>
            <button type="button" className={`pill ${voice.handsFree ? 'on' : ''}`} aria-pressed={voice.handsFree} onClick={() => voice.setHandsFree(!voice.handsFree)} title="Listen again after each reply">
              Hands-free
            </button>
            <button type="button" className="pill" onClick={toggleVoice}>Keyboard</button>
          </div>
        </div>
      ) : (
        <form className="composer" onSubmit={send}>
          <textarea
            ref={input}
            rows={1}
            value={draft}
            placeholder={disabled ? 'Connecting…' : 'Message the building'}
            disabled={disabled}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) send(event)
            }}
          />
          {!draft.trim() ? (
            <VoiceOrb state={pending ? 'thinking' : 'off'} level={voice.level} size={40} className="orb-mini" disabled={disabled} onClick={toggleVoice} label="Talk to the building" />
          ) : (
            <button type="submit" disabled={!draft.trim() || pending || disabled} aria-label="Send">
              <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
                <path d="M8 13V3M3.5 7.5 8 3l4.5 4.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          )}
        </form>
      )}

      {walking && createPortal(
        <CameraGuide
          route={walking}
          lang={voice.lang}
          ask={async (text, photo) => {
            const reply = await onSend(text, { channel: 'voice', photo })
            if (!reply) throw new Error('no reply')
            return { text: reply.reply.replace(RAW_ID, ''), spoken: reply.spoken }
          }}
          onClose={() => setWalking(null)}
        />,
        document.body,
      )}
    </section>
  )
}
