// The Edit mode's bar, under the building screen's top line (right of it on wide screens, left of the settings
// corner): that you are editing a copy and how many changes, the tools (Select / Add door / Add item, and Access
// for the admin in access mode), the validator's problems, undo / redo, start
// again from the original (asks once more), Save as a new building and Done. The conversation with the Builder is the Guide's card (building/Guide.tsx), the inspector for
// what is selected is shown in it (EditCard).

import { Check, DoorOpen, Lock, MapPin, MousePointer2, Plus, Ruler, Package, Redo2, RotateCcw, TriangleAlert, Undo2, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { Issue } from '../api'
import type { Draft } from './useDraft'
import type { Tool } from './types'
import './edit.css'

const TOOLS: { tool: Tool; key: string; label: string; Icon: typeof MousePointer2 }[] = [
  { tool: 'select', key: 'V', label: 'Select', Icon: MousePointer2 },
  { tool: 'door', key: 'D', label: 'Door', Icon: DoorOpen },
  { tool: 'item', key: 'I', label: 'Item', Icon: Package },
  { tool: 'access', key: 'A', label: 'Access', Icon: Lock },
]

type Props = {
  draft: Draft
  onFocusIssue: (issue: Issue) => void
  onDone: () => void
  onSave: (name: string) => void
  /** offer the Access tool (access mode, the admin) */
  accessTool: boolean
  onPlace?: () => void // the building has a map position: move / turn / scale it on the map
  onAddFloor?: () => void // new floors from plans, into this draft
  onStraighten?: () => void // turn the floor shown so its walls run parallel to the lowest floor's
}

export function EditBar({ draft, onFocusIssue, onDone, onSave, accessTool, onPlace, onAddFloor, onStraighten }: Props) {
  const { state, busy, tool, setTool } = draft
  const [problems, setProblems] = useState(false)
  const [naming, setNaming] = useState<string | null>(null)
  // "Discard changes" asks once more in place (no browser dialog); the question goes away by itself
  const [discarding, setDiscarding] = useState(false)
  useEffect(() => {
    if (!discarding) return
    const timer = setTimeout(() => setDiscarding(false), 4000)
    return () => clearTimeout(timer)
  }, [discarding])
  if (!state) {
    return (
      <div className="edit-bar" role="toolbar" aria-label="Edit">
        <p className={`edit-status${draft.failed ? ' failed' : ''}`} role={draft.failed ? 'alert' : 'status'}>
          {draft.failed ? `Could not edit: ${draft.failed}` : 'Making an editable copy…'}
        </p>
        <button type="button" className="edit-done" onClick={onDone}>{draft.failed ? 'Close' : 'Cancel'}</button>
      </div>
    )
  }
  const changes = state.draft.steps
  const errors = state.issues.filter((issue) => issue.severity === 'error')
  const warnings = state.issues.filter((issue) => issue.severity === 'warning')

  return (
    <>
      <div className="edit-bar" role="toolbar" aria-label="Edit">
        <div className="edit-tools" role="radiogroup" aria-label="Tool">
          {TOOLS.filter(({ tool: value }) => value !== 'access' || accessTool).map(({ tool: value, key, label, Icon }) => (
            <button key={value} type="button" role="radio" aria-checked={tool === value} title={`${label} (${key})`} onClick={() => setTool(value)}>
              <Icon size={16} strokeWidth={2} />
              <span>{label}</span>
            </button>
          ))}
        </div>
        <button type="button" className={`edit-problems${errors.length ? ' has-errors' : ''}`} aria-expanded={problems}
          onClick={() => setProblems((open) => !open)} title={errors.length ? 'Problems your changes made' : 'Your changes broke nothing'}>
          {errors.length ? <TriangleAlert size={15} strokeWidth={2.2} /> : <Check size={15} strokeWidth={2.4} />}
          <span>{errors.length ? `${errors.length} ${errors.length === 1 ? 'problem' : 'problems'}` : 'No problems'}</span>
        </button>
        <button type="button" className="edit-icon" onClick={draft.undo} disabled={busy || changes === 0} aria-label="Undo" title="Undo (⌘Z)">
          <Undo2 size={16} strokeWidth={2} />
        </button>
        <button type="button" className="edit-icon edit-redo" onClick={draft.redo} disabled={busy || !draft.canRedo} aria-label="Redo" title="Redo (⇧⌘Z)">
          <Redo2 size={16} strokeWidth={2} />
        </button>
        {discarding ? (
          <button type="button" className="edit-discard" onClick={() => { setDiscarding(false); void draft.discard() }} disabled={busy}>
            Discard {changes} {changes === 1 ? 'change' : 'changes'}?
          </button>
        ) : (
          <button type="button" className="edit-icon" onClick={() => setDiscarding(true)} disabled={busy || changes === 0}
            aria-label="Discard changes" title="Discard all changes and start again from the original building">
            <RotateCcw size={16} strokeWidth={2} />
          </button>
        )}
        {onStraighten && (
          <button type="button" className="edit-icon" onClick={onStraighten} disabled={busy}
            aria-label="Straighten this floor" title="Straighten this floor (walls parallel to the lowest floor)">
            <Ruler size={16} strokeWidth={2} />
          </button>
        )}
        {onAddFloor && (
          <button type="button" className="edit-icon" onClick={onAddFloor} disabled={busy} aria-label="Add a floor from plans"
            title="Add a floor from plans">
            <Plus size={16} strokeWidth={2} />
          </button>
        )}
        {onPlace && (
          <button type="button" className="edit-icon" onClick={onPlace} disabled={busy} aria-label="Edit position on the map"
            title="Edit position on the map">
            <MapPin size={16} strokeWidth={2} />
          </button>
        )}
        <button type="button" className="edit-save-button" disabled={busy || changes === 0}
          title={changes === 0 ? 'Make a change first' : 'Save as a new building'} onClick={() => setNaming(`${state.draft.name} (edited)`)}>
          Save
        </button>
        <button type="button" className="edit-done" onClick={onDone} disabled={busy} title="Stop editing — the draft is kept" aria-label="Done">
          <Check size={16} strokeWidth={2.4} className="edit-done-icon" />
          <span>Done</span>
        </button>
      </div>
      {draft.message && (
        <p className="edit-toast" role="alert">
          {draft.message}
          <button type="button" onClick={() => draft.setMessage(null)} aria-label="Dismiss"><X size={14} /></button>
        </p>
      )}

      {problems && (
        <>
          <div className="hud-scrim" onClick={() => setProblems(false)} />
          <section className="edit-issues" aria-label="Problems">
            <p className="who">{errors.length ? 'Problems from your changes' : 'Your changes broke nothing'}</p>
            {errors.map((issue, i) => (
              <button key={`e${i}`} type="button" className="issue error" onClick={() => { onFocusIssue(issue); setProblems(false) }}>{issue.message}</button>
            ))}
            {warnings.length > 0 && <p className="who">Already in the original · {warnings.length}</p>}
            {warnings.slice(0, 12).map((issue, i) => (
              <button key={`w${i}`} type="button" className="issue warning" onClick={() => { onFocusIssue(issue); setProblems(false) }}>{issue.message}</button>
            ))}
          </section>
        </>
      )}

      {naming !== null && (
        <>
          <div className="edit-scrim" onClick={() => setNaming(null)} />
          <form
            className="edit-save"
            onSubmit={(event) => {
              event.preventDefault()
              onSave(naming)
            }}
          >
            <p className="inspector-title">Save as a new building</p>
            <p className="inspector-note">The original stays as it is. The edited copy opens next, and the Guide answers about it.</p>
            <input autoFocus value={naming} onChange={(event) => setNaming(event.target.value)} aria-label="Building name"
              onKeyDown={(event) => event.key === 'Escape' && setNaming(null)} />
            {errors.length > 0 && <p className="warn">{errors.length} open {errors.length === 1 ? 'problem' : 'problems'} — you can save anyway.</p>}
            <div className="row">
              <button type="button" className="edit-card-button" onClick={() => setNaming(null)}>Cancel</button>
              <button type="submit" className="edit-primary" disabled={busy || !naming.trim()}>{errors.length > 0 ? 'Save anyway' : 'Save'}</button>
            </div>
          </form>
        </>
      )}
    </>
  )
}
