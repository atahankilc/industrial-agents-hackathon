// Edit mode (docs/superpowers/specs/2026-10-24-builder-edit-mode-design.md §5): a draft copy of the building,
// a 2D plan editor for one floor, a live 3D preview inset, the validator's issues, undo and save.
// The draft id is kept in localStorage per base building, so a reload resumes the same draft.

import { ChevronLeft, Undo2 } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, type BuilderReply, type DraftState, type Issue, type Op, type Plan, type Proposal } from '../api'
import type { PlanPalette } from '../plan/palette'
import { PlanView } from '../plan/PlanView'
import { DEFAULT_SETTINGS } from '../plan/settings'
import { BuilderChat } from './BuilderChat'
import { PlanEditor, type Selection } from './PlanEditor'
import './edit.css'

const NO_INSETS = { top: 0, right: 0, bottom: 0, left: 0 }
const PREVIEW_SETTINGS = { ...DEFAULT_SETTINGS, pins: false, hover: false }
const ignore = () => {}
const draftKey = (base: string) => `draft:${base}`

// One open request per base building: a second mount while the first is still loading (React StrictMode runs
// effects twice) must get the same draft, or two drafts are created and localStorage keeps the wrong one.
const opening = new Map<string, Promise<DraftState>>()

function openDraft(base: string): Promise<DraftState> {
  const pending = opening.get(base)
  if (pending) return pending
  const work = (async () => {
    const stored = localStorage.getItem(draftKey(base))
    const resumed = stored ? await api.draft(stored).catch(() => null) : null
    if (resumed) return resumed
    const created = await api.createDraft(base)
    localStorage.setItem(draftKey(base), created.draft.id)
    return created
  })().finally(() => opening.delete(base))
  opening.set(base, work)
  return work
}

type Props = {
  base: string
  palette: PlanPalette // the building screen's light / dark palette, for the 3D preview
  onSaved: (building: string, name: string) => void
  onExit: () => void
}

/** "422 /drafts/x/ops: {"detail":"…"}" → "…" */
function reason(error: unknown) {
  const text = String(error instanceof Error ? error.message : error)
  const match = text.match(/"detail":\s*"((?:[^"\\]|\\.)*)"/)
  return match ? JSON.parse(`"${match[1]}"`) : text.replace(/^Error:\s*/, '')
}

export function EditMode({ base, palette, onSaved, onExit }: Props) {
  const [state, setState] = useState<DraftState | null>(null)
  const [floorId, setFloorId] = useState<string | null>(null)
  const [plan, setPlan] = useState<Plan | null>(null)
  const [selected, setSelected] = useState<Selection>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [revision, setRevision] = useState(0) // bumped on every op response, applied or refused
  const [naming, setNaming] = useState<string | null>(null) // save dialog open: the name being typed
  const [proposal, setProposal] = useState<Proposal | null>(null) // the Builder's open proposal, drawn as a ghost

  // Open (or resume) the draft for this base building.
  useEffect(() => {
    let cancelled = false
    setState(null)
    const open = async () => {
      const next = await openDraft(base)
      if (cancelled) return
      setState(next)
      const floors = [...next.building.floors].sort((a, b) => a.level - b.level)
      setFloorId((floors.find((floor) => floor.level === 0) ?? floors[0])?.id ?? null)
    }
    open().catch((error) => !cancelled && setMessage(reason(error)))
    return () => {
      cancelled = true
    }
  }, [base])

  // 3D preview follows every change.
  const draftId = state?.draft.id
  useEffect(() => {
    if (!draftId) return
    let cancelled = false
    api.draftPlan(draftId).then((next) => !cancelled && setPlan(next)).catch(() => {})
    return () => {
      cancelled = true
    }
  }, [draftId, state])

  const run = useCallback(async (work: () => Promise<DraftState>) => {
    setBusy(true)
    try {
      setState(await work())
      setMessage(null)
    } catch (error) {
      setMessage(reason(error))
      // 409: the draft moved on elsewhere (another tab or server instance) — show where it is now.
      if (draftId && String(error).includes('409 ')) {
        const latest = await api.draft(draftId).catch(() => null)
        if (latest) setState(latest)
      }
    } finally {
      setBusy(false)
      setRevision((value) => value + 1)
    }
  }, [draftId])

  // A hand edit makes an open proposal stale (the backend would refuse it), so it is dropped.
  const onOps = useCallback((ops: Op[]) => {
    if (!draftId || busy) return
    setProposal(null)
    void run(() => api.applyOps(draftId, ops))
  }, [draftId, busy, run])
  const undo = useCallback(() => {
    if (!draftId || busy || !state || state.draft.steps === 0) return
    setProposal(null)
    void run(() => api.undo(draftId))
  }, [draftId, busy, state, run])

  const onReply = (reply: BuilderReply) => {
    setState(reply.state)
    setProposal(reply.proposal)
    if (!reply.proposal) return
    // show the floor the proposal touches
    const before = reply.state.building
    const after = reply.proposal.building
    const changed = [
      ...after.spaces.filter((item) => JSON.stringify(item) !== JSON.stringify(before.spaces.find((old) => old.id === item.id))),
      ...after.openings.filter((item) => JSON.stringify(item) !== JSON.stringify(before.openings.find((old) => old.id === item.id))),
      ...after.assets.filter((item) => JSON.stringify(item) !== JSON.stringify(before.assets.find((old) => old.id === item.id))),
    ]
    if (changed[0]) setFloorId(changed[0].floor_id)
  }

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'z' && !(event.target instanceof HTMLInputElement)) {
        event.preventDefault()
        undo()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [undo])

  const save = async (name: string) => {
    if (!draftId) return
    setBusy(true)
    try {
      const saved = await api.saveDraft(draftId, name)
      localStorage.removeItem(draftKey(base))
      onSaved(saved.building, name)
    } catch (error) {
      setMessage(reason(error))
      setBusy(false)
    }
  }

  const floors = useMemo(() => [...(state?.building.floors ?? [])].sort((a, b) => b.level - a.level), [state])
  const examples = useMemo(() => {
    const rooms = (state?.building.spaces ?? []).filter((space) => space.type === 'room' && space.ref)
    if (rooms.length < 2) return []
    return [`Make ${rooms[0].ref} 1 m wider to the east`, `Rename ${rooms[1].ref} to Quiet room`]
  }, [state])
  const currentFloor = state?.building.floors.find((floor) => floor.id === floorId)
  const errors = state?.issues.filter((issue) => issue.severity === 'error') ?? []
  const warnings = state?.issues.filter((issue) => issue.severity === 'warning') ?? []

  const focusIssue = (issue: Issue) => {
    if (!state) return
    const id = issue.ids[0]
    const space = state.building.spaces.find((item) => item.id === id)
    const opening = state.building.openings.find((item) => item.id === id)
    const asset = state.building.assets.find((item) => item.id === id)
    const target = space ?? opening ?? asset
    if (!target) return
    setFloorId(target.floor_id)
    setSelected({ kind: space ? 'space' : opening ? 'opening' : 'asset', id })
  }

  if (!state || !floorId) {
    return (
      <div className="edit loading">
        {message ? <p className="error">{message}</p> : <p className="muted pulse">Copying building…</p>}
      </div>
    )
  }

  return (
    <div className="edit">
      <header className="guide-line edit-line">
        <button type="button" className="round" onClick={onExit} disabled={busy} aria-label="Back to the building"
          title="Back to the building (the draft is kept)">
          <ChevronLeft size={20} strokeWidth={2.2} />
        </button>
        <div className="where">
          <h1>Editing {state.draft.name}</h1>
          <p>
            Draft copy · {state.draft.steps} {state.draft.steps === 1 ? 'change' : 'changes'}
            {currentFloor ? ` · ${currentFloor.name}` : ''}
          </p>
        </div>
        <button type="button" className="round" onClick={undo} disabled={busy || state.draft.steps === 0}
          aria-label="Undo" title="Undo (⌘Z)">
          <Undo2 size={19} strokeWidth={2} />
        </button>
        <button type="button" className="edit-save-button" onClick={() => setNaming(`${state.draft.name} (edited)`)} disabled={busy}>
          Save
        </button>
      </header>
      {message && <p className="edit-message" role="status">{message}</p>}

      <PlanEditor
        building={state.building}
        floorId={floorId}
        issues={state.issues}
        selected={selected}
        onSelect={setSelected}
        onOps={onOps}
        busy={busy}
        revision={revision}
        ghost={proposal?.building ?? null}
        palette={palette}
      />

      {floors.length > 1 && (
        <nav className="floor-tabs edit-floors" aria-label="Floors">
          {floors.map((floor) => (
            <button key={floor.id} type="button" aria-pressed={floor.id === floorId} aria-label={floor.name}
              onClick={() => setFloorId(floor.id)}>
              {floor.level < 0 ? `B${-floor.level}` : floor.level === 0 ? 'G' : floor.level}
            </button>
          ))}
        </nav>
      )}

      <div className="edit-inset" aria-label="3D preview">
        {plan && (
          <PlanView
            plan={plan}
            floor={Math.max(0, plan.floors.findIndex((floor) => floor.id === floorId))}
            stacked={false}
            palette={palette}
            selected={null}
            insets={NO_INSETS}
            fitKey={0}
            onSelect={ignore}
            onPickFloor={ignore}
            onTilt={ignore}
            spread
            settings={PREVIEW_SETTINGS}
          />
        )}
      </div>

      <BuilderChat
        draftId={state.draft.id}
        proposal={proposal}
        disabled={busy}
        examples={examples}
        onReply={onReply}
        onApplied={(next) => {
          setProposal(null)
          setState(next)
          setRevision((value) => value + 1)
        }}
        onCancel={() => setProposal(null)}
      />

      <aside className="edit-issues">
        <p className="label">{errors.length === 0 ? 'No problems' : `${errors.length} ${errors.length === 1 ? 'problem' : 'problems'}`}</p>
        {[...errors, ...warnings].slice(0, 30).map((issue, i) => (
          <button key={i} type="button" className={`issue ${issue.severity}`} onClick={() => focusIssue(issue)}>
            {issue.message}
          </button>
        ))}
        <p className="muted hint">Click a room to drag its corners · drag doors along walls · drag things · R rotates</p>
      </aside>

      {naming !== null && (
        <form
          className="edit-save"
          onSubmit={(event) => {
            event.preventDefault()
            save(naming)
          }}
        >
          <p className="label">Save as a new building</p>
          <input autoFocus value={naming} onChange={(event) => setNaming(event.target.value)} aria-label="Building name" />
          {errors.length > 0 && <p className="warn">{errors.length} open {errors.length === 1 ? 'problem' : 'problems'} — you can save anyway.</p>}
          <div className="row">
            <button type="button" className="edit-card-button" onClick={() => setNaming(null)}>Cancel</button>
            <button type="submit" className="edit-primary" disabled={busy || !naming.trim()}>{errors.length > 0 ? 'Save anyway' : 'Save'}</button>
          </div>
        </form>
      )}
    </div>
  )
}
