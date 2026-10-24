// Edit mode (docs/superpowers/specs/2026-10-24-builder-edit-mode-design.md §5): a draft copy of the building,
// a 2D plan editor for one floor, a live 3D preview inset, the validator's issues, undo and save.
// The draft id is kept in localStorage per base building, so a reload resumes the same draft.

import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, type DraftState, type Issue, type Op, type Plan } from '../api'
import type { PlanPalette } from '../plan/palette'
import { PlanView } from '../plan/PlanView'
import { DEFAULT_SETTINGS } from '../plan/settings'
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
    } finally {
      setBusy(false)
      setRevision((value) => value + 1)
    }
  }, [])

  const onOps = useCallback((ops: Op[]) => draftId && !busy && run(() => api.applyOps(draftId, ops)), [draftId, busy, run])
  const undo = useCallback(
    () => draftId && !busy && state && state.draft.steps > 0 && run(() => api.undo(draftId)),
    [draftId, busy, state, run],
  )

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
      <div className="edit-strip">
        <span className="label">Draft</span>
        <span>Copy of {state.draft.name}</span>
        <span className="muted">· {state.draft.steps} {state.draft.steps === 1 ? 'change' : 'changes'}</span>
        <button type="button" onClick={undo} disabled={busy || state.draft.steps === 0} title="Undo (⌘Z)">↶ Undo</button>
        <button type="button" className="edit-primary" onClick={() => setNaming(`${state.draft.name} (edited)`)} disabled={busy}>Save</button>
        <button type="button" onClick={onExit} disabled={busy} title="Back to the building (the draft is kept)">Done</button>
        {message && <span className="edit-message">{message}</span>}
      </div>

      <PlanEditor
        building={state.building}
        floorId={floorId}
        issues={state.issues}
        selected={selected}
        onSelect={setSelected}
        onOps={onOps}
        busy={busy}
        revision={revision}
      />

      <nav className="hud floors edit-floors" aria-label="Floors">
        {floors.map((floor) => (
          <button key={floor.id} type="button" className={floor.id === floorId ? 'on' : ''} onClick={() => setFloorId(floor.id)} title={floor.name}>
            {floor.level}
          </button>
        ))}
      </nav>

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
            <button type="button" onClick={() => setNaming(null)}>Cancel</button>
            <button type="submit" className="edit-primary" disabled={busy || !naming.trim()}>{errors.length > 0 ? 'Save anyway' : 'Save'}</button>
          </div>
        </form>
      )}
    </div>
  )
}
