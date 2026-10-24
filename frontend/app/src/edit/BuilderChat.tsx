// The Edit mode's chat with the Builder agent (agent/builder.py): type a change, watch what it looks at, then
// review its proposal — summary, area changes, problems it would add — and Apply or Cancel. The plan shows the
// same proposal as a ghost (EditMode passes `proposal.building` to PlanEditor). A plain "yes" also applies.

import { ArrowUp, Check, Loader2, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api, type BuilderReply, type BuilderStep, type DraftState, type Proposal } from '../api'

type Line = { role: 'user' | 'builder' | 'note'; text: string }

type Props = {
  draftId: string
  proposal: Proposal | null
  disabled: boolean // a drag / undo is in flight
  examples: string[] // starter prompts built from this building's rooms
  onReply: (reply: BuilderReply) => void
  onApplied: (state: DraftState) => void
  onCancel: () => void
}

const clip = (value: unknown) => {
  const text = String(value ?? '')
  return text.length > 28 ? `${text.slice(0, 27)}…` : text
}

function stepText(step: BuilderStep): string {
  if (step.kind === 'check') return 'Double-checking numbers against the building'
  const input = step.input ?? {}
  switch (step.name) {
    case 'overview': return 'Reading the building'
    case 'find': return `Looking for “${clip(input.query)}”`
    case 'space_info': return `Looking at ${clip(input.space)}`
    case 'floor_plan': return 'Reading the floor layout'
    case 'propose_edit': return 'Trying the change on a copy'
    default: return 'Working'
  }
}

export function BuilderChat({ draftId, proposal, disabled, examples, onReply, onApplied, onCancel }: Props) {
  const [lines, setLines] = useState<Line[]>([])
  const [text, setText] = useState('')
  const [pending, setPending] = useState(false)
  const [step, setStep] = useState<string | null>(null)
  const [applying, setApplying] = useState(false)
  const list = useRef<HTMLDivElement>(null)

  useEffect(() => {
    list.current?.scrollTo({ top: list.current.scrollHeight })
  }, [lines, step, proposal])

  const send = async (message: string) => {
    const value = message.trim()
    if (!value || pending) return
    setText('')
    setLines((current) => [...current, { role: 'user', text: value }])
    setPending(true)
    setStep('Thinking')
    try {
      const reply = await api.builderStream(draftId, value, (next) => next.kind !== 'tool_done' && setStep(stepText(next)))
      setLines((current) => [...current, { role: 'builder', text: reply.reply }])
      onReply(reply)
    } catch (reason) {
      setLines((current) => [...current, { role: 'note', text: `The Builder could not answer: ${String(reason)}` }])
    } finally {
      setPending(false)
      setStep(null)
    }
  }

  const apply = async () => {
    if (!proposal) return
    setApplying(true)
    try {
      const state = await api.applyProposal(draftId, proposal.id)
      setLines((current) => [...current, { role: 'note', text: `Applied: ${proposal.summary}` }])
      onApplied(state)
    } catch (reason) {
      const detail = String(reason).match(/"detail":\s*"([^"]*)"/)?.[1] ?? String(reason)
      setLines((current) => [...current, { role: 'note', text: `Not applied: ${detail}` }])
      onCancel()
    } finally {
      setApplying(false)
    }
  }

  // Cancel closes the proposal on the server too, so a later "yes" can't apply it.
  const cancel = () => {
    if (proposal) void api.cancelProposal(draftId, proposal.id).catch(() => {})
    onCancel()
  }

  return (
    <section className="builder" aria-label="Builder">
      <div className="builder-lines" ref={list}>
        {lines.length === 0 && (
          <div className="builder-empty">
            <p>Tell me what to change. I'll show it on the plan first; nothing changes until you apply.</p>
            {examples.map((example) => (
              <button key={example} type="button" className="builder-chip" onClick={() => setText(example)}>
                {example}
              </button>
            ))}
          </div>
        )}
        {lines.map((line, index) => (
          <p key={index} className={`builder-line from-${line.role}`}>{line.text}</p>
        ))}
        {step && (
          <p className="builder-line step">
            <Loader2 size={14} className="spin" /> {step}
          </p>
        )}
        {proposal && (
          <article className="builder-proposal">
            <p className="label">Proposal</p>
            <p className="summary">{proposal.summary}</p>
            {proposal.effect.changed_spaces.map((item) => (
              <p key={item.id} className="area">
                {item.name}: {item.area_before} → {item.area_after} m²
              </p>
            ))}
            {proposal.new_problems.map((problem, index) => (
              <p key={index} className="problem">{problem}</p>
            ))}
            <div className="row">
              <button type="button" className="edit-card-button" onClick={cancel} disabled={applying}>
                <X size={14} /> Cancel
              </button>
              <button type="button" className="edit-primary" onClick={apply} disabled={applying || disabled}>
                <Check size={14} /> {proposal.new_problems.length ? 'Apply anyway' : 'Apply'}
              </button>
            </div>
          </article>
        )}
      </div>
      <form
        className="builder-ask"
        onSubmit={(event) => {
          event.preventDefault()
          void send(text)
        }}
      >
        <input
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder="Describe a change…"
          aria-label="Describe a change"
          disabled={pending}
        />
        <button type="submit" className="edit-primary" disabled={pending || !text.trim()} aria-label="Send">
          <ArrowUp size={16} />
        </button>
      </form>
    </section>
  )
}
