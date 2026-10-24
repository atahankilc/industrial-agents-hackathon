// Edit mode (docs/superpowers/specs/2026-10-24-builder-edit-mode-design.md §5): a draft copy of the building,
// a 2D plan editor for one floor, a live 3D preview inset, the validator's issues, undo and save.
// The draft id is kept in localStorage per base building, so a reload resumes the same draft.

import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, type DraftState, type Issue, type Op, type PointCloud } from '../api'
import { Scene } from '../scene/Scene'
import { PlanEditor, type Selection } from './PlanEditor'
import './edit.css'

const EMPTY_SETS = { highlight: [], lost: [], closed: [], route: [] }
const draftKey = (base: string) => `draft:${base}`

type Props = {
  base: string
  dark: boolean
  onSaved: (building: string, name: string) => void
}

/** "422 /drafts/x/ops: {"detail":"…"}" → "…" */
function reason(error: unknown) {
  const text = String(error instanceof Error ? error.message : error)
  const match = text.match(/"detail":\s*"((?:[^"\\]|\\.)*)"/)
  return match ? JSON.parse(`"${match[1]}"`) : text.replace(/^Error:\s*/, '')
}

export function EditMode({ base, dark, onSaved }: Props) {
  const [state, setState] = useState<DraftState | null>(null)
  const [floorId, setFloorId] = useState<string | null>(null)
  const [cloud, setCloud] = useState<PointCloud | null>(null)
  const [selected, setSelected] = useState<Selection>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [naming, setNaming] = useState<string | null>(null) // save dialog open: the name being typed

  // Open (or resume) the draft for this base building.
  useEffect(() => {
    let cancelled = false
    setState(null)
    const open = async () => {
      const stored = localStorage.getItem(draftKey(base))
      let next: DraftState | null = null
      if (stored) next = await api.draft(stored).catch(() => null)
      if (!next) {
        next = await api.createDraft(base)
        localStorage.setItem(draftKey(base), next.draft.id)
      }
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
    api.draftPoints(draftId).then((points) => !cancelled && setCloud(points)).catch(() => {})
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
    }
  }, [])

  const onOps = useCallback((ops: Op[]) => draftId && run(() => api.applyOps(draftId, ops)), [draftId, run])
  const undo = useCallback(() => draftId && state && state.draft.steps > 0 && run(() => api.undo(draftId)), [draftId, state, run])

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
        <button type="button" className="primary" onClick={() => setNaming(`${state.draft.name} (edited)`)} disabled={busy}>Save</button>
        {message && <span className="edit-message">{message}</span>}
      </div>

      <PlanEditor
        building={state.building}
        floorId={floorId}
        issues={state.issues}
        selected={selected}
        onSelect={setSelected}
        onOps={onOps}
      />

      <nav className="hud floors edit-floors" aria-label="Floors">
        {floors.map((floor) => (
          <button key={floor.id} type="button" className={floor.id === floorId ? 'on' : ''} onClick={() => setFloorId(floor.id)} title={floor.name}>
            {floor.level}
          </button>
        ))}
      </nav>

      <div className="edit-inset" aria-label="3D preview">
        {cloud && (
          <Scene cloud={cloud} dark={dark} sets={EMPTY_SETS} floorsOn={cloud.floors.map(() => true)} explode={0} density={0.3}
            emergeKey={0} route={null} focus={null} inset />
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
            <button type="submit" className="primary" disabled={busy || !naming.trim()}>{errors.length > 0 ? 'Save anyway' : 'Save'}</button>
          </div>
        </form>
      )}
    </div>
  )
}
