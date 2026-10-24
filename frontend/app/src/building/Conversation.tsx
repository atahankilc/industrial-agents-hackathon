// The conversation, kept out of the way: an ask bar floating at the bottom (bottom-left on wide screens) and, above
// it, only the latest exchange — what you wrote or said, and what the Guide answered or spoke. Earlier turns fold
// into an "Earlier" pill that opens them. Before the first question, a row of starter chips sits above the bar.
// A tapped room or object shows its card in the same place.

import { Accessibility, ArrowUp, Bath, ChevronDown, ChevronUp, CircleHelp, DoorOpen, Layers, Loader2, Mic, Navigation, UtensilsCrossed, Volume2, X } from 'lucide-react'
import { useState, type ReactNode } from 'react'

export type Message =
  | { role: 'user'; text: string; spoken?: boolean }
  | { role: 'guide'; text: string; live?: boolean; step?: string; spoken?: boolean }
  | { role: 'note'; text: string }

export type Suggestion = { label: string; prompt: string; icon: 'toilet' | 'exit' | 'access' | 'food' | 'floor' | 'help' }

export type InfoCard = { title: string; meta: string; detail?: string; directions?: string }

type Props = {
  messages: Message[]
  pending: boolean
  listening: boolean
  canListen: boolean
  info: InfoCard | null
  suggestions: Suggestion[]
  onSend: (text: string) => void
  onListen: () => void
  onCloseInfo: () => void
  onClear: () => void
}

const ICONS = { toilet: Bath, exit: DoorOpen, access: Accessibility, food: UtensilsCrossed, floor: Layers, help: CircleHelp }

export function Conversation({ messages, pending, listening, canListen, info, suggestions, onSend, onListen, onCloseInfo, onClear }: Props) {
  const [draft, setDraft] = useState('')
  const [history, setHistory] = useState(false)

  const submit = (text: string) => {
    const value = text.trim()
    if (!value || pending) return
    onSend(value)
    setDraft('')
  }

  // the latest exchange starts at the last thing the user said
  const lastUser = messages.map((message) => message.role).lastIndexOf('user')
  const latest = lastUser >= 0 ? messages.slice(lastUser) : messages
  const earlier = lastUser > 0 ? messages.slice(0, lastUser) : []
  const shown = history ? messages : latest

  return (
    <section className="talk" aria-label="Guide">
      {info && (
        <article className="card info">
          <header>
            <div>
              <h2>{info.title}</h2>
              <p>{info.meta}</p>
              {info.detail && <p className="detail">{info.detail}</p>}
            </div>
            <button type="button" className="icon-button" onClick={onCloseInfo} aria-label="Close">
              <X size={17} />
            </button>
          </header>
          {info.directions && (
            <button type="button" className="primary" onClick={() => submit(info.directions!)}>
              <Navigation size={16} strokeWidth={2.2} aria-hidden="true" />
              Directions
            </button>
          )}
        </article>
      )}

      {!info && shown.length > 0 && (
        <div className="card thread-card">
          <div className="thread-tools">
            {earlier.length > 0 && (
              <button type="button" className="pill" onClick={() => setHistory((open) => !open)}>
                {history ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
                {history ? 'Latest only' : `Earlier (${earlier.filter((m) => m.role === 'user').length})`}
              </button>
            )}
            <button type="button" className="icon-button small" onClick={onClear} aria-label="Hide the conversation">
              <X size={15} />
            </button>
          </div>
          <ol className={`thread ${history ? 'open' : ''}`}>
            {shown.map((message, index) => (
              <li key={index} className={`turn ${message.role}`}>
                {message.role !== 'note' && message.spoken && <Volume2 className="spoken" size={13} aria-label="spoken" />}
                {message.role === 'guide' && message.live ? (
                  <p className="working">
                    <Loader2 className="spin" size={15} />
                    <span>{message.step ?? 'Looking at the building…'}</span>
                  </p>
                ) : (
                  paragraphs(message.text)
                )}
              </li>
            ))}
          </ol>
        </div>
      )}

      {!info && messages.length === 0 && (
        <ul className="chips" aria-label="Suggestions">
          {suggestions.map((item) => (
            <li key={item.label}>
              <Chip icon={ICONS[item.icon]} onClick={() => submit(item.prompt)}>
                {item.label}
              </Chip>
            </li>
          ))}
        </ul>
      )}

      <form
        className="ask"
        onSubmit={(event) => {
          event.preventDefault()
          submit(draft)
        }}
      >
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder={listening ? 'Listening…' : 'Ask the building'}
          aria-label="Ask the building"
          enterKeyHint="send"
        />
        {draft.trim() ? (
          <button type="submit" className="ask-send" disabled={pending} aria-label="Send">
            {pending ? <Loader2 className="spin" size={18} /> : <ArrowUp size={18} strokeWidth={2.4} />}
          </button>
        ) : (
          canListen && (
            <button type="button" className={`ask-mic ${listening ? 'on' : ''}`} onClick={onListen} disabled={pending} aria-label={listening ? 'Stop listening' : 'Speak'}>
              <Mic size={18} strokeWidth={2.2} />
            </button>
          )
        )}
      </form>
    </section>
  )
}

function Chip({ icon: Icon, children, onClick }: { icon: typeof Bath; children: ReactNode; onClick: () => void }) {
  return (
    <button type="button" className="chip" onClick={onClick}>
      <Icon size={15} strokeWidth={2} aria-hidden="true" />
      <span>{children}</span>
    </button>
  )
}

/** Guide replies are short prose; drop markdown emphasis markers and keep paragraphs. */
function paragraphs(text: string) {
  return text
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .split(/\n{2,}/)
    .map((part, index) => <p key={index}>{part.trim()}</p>)
}
