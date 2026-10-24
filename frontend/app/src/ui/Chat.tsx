// Conversation panel: the Guide's replies (light markdown: paragraphs, numbered/bulleted lines, **bold**),
// a thinking indicator while tools run, and one-tap suggestions on an empty conversation.

import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'

export type Message = { role: 'user' | 'guide' | 'note'; text: string }

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

function Thinking() {
  const [seconds, setSeconds] = useState(0)
  useEffect(() => {
    const started = performance.now()
    const timer = setInterval(() => setSeconds(Math.floor((performance.now() - started) / 1000)), 500)
    return () => clearInterval(timer)
  }, [])
  return (
    <div className="message guide thinking" aria-label="The guide is working">
      <span className="dots"><i /><i /><i /></span>
      {seconds >= 3 && <span className="muted">checking the building · {seconds}s</span>}
    </div>
  )
}

type Props = { messages: Message[]; pending: boolean; disabled: boolean; onSend: (text: string) => void }

export function Chat({ messages, pending, disabled, onSend }: Props) {
  const [draft, setDraft] = useState('')
  const log = useRef<HTMLDivElement>(null)
  const input = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    log.current?.scrollTo({ top: log.current.scrollHeight, behavior: 'smooth' })
  }, [messages, pending])

  const send = (event?: FormEvent) => {
    event?.preventDefault()
    const text = draft.trim()
    if (!text || pending || disabled) return
    onSend(text)
    setDraft('')
  }

  return (
    <section className="chat" aria-label="Conversation with the building guide">
      <div className="log" ref={log} aria-live="polite">
        {messages.length === 0 && (
          <div className="empty">
            <p className="lead">Ask the building.</p>
            <p className="muted">Find things, get step-by-step directions, report what is broken.</p>
            <div className="suggestions">
              {SUGGESTIONS.map((text) => (
                <button key={text} type="button" disabled={disabled} onClick={() => onSend(text)}>
                  {text}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((message, index) => (
          <div key={index} className={`message ${message.role}`}>
            {message.role === 'guide' ? <Rich text={message.text} /> : <p>{message.text}</p>}
          </div>
        ))}
        {pending && <Thinking />}
      </div>
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
        <button type="submit" disabled={!draft.trim() || pending || disabled} aria-label="Send">
          <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
            <path d="M8 13V3M3.5 7.5 8 3l4.5 4.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </form>
    </section>
  )
}
