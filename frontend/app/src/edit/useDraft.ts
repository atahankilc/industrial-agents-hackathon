// Edit mode state for the building screen (docs/superpowers/specs/2026-10-24-builder-edit-mode-design.md §5): the
// draft copy of the building, its plan (the model the building screen draws while editing), the selection, the
// tool, the conversation with the Builder (agent/builder.py, shown in the Guide's card: building/Guide.tsx) and its
// open proposal, undo / redo, start over and save.
// Redo is kept here, not on the server: the ops behind the last steps made in this tab are remembered, undo moves
// them to a redo stack, redo sends them again; any other change (or a change from elsewhere) clears it. Ops go to /drafts/{id}/ops; the backend applies, snaps and
// validates (core/edits.py, core/validate.py). The draft id is kept in localStorage per base building, so a
// reload resumes the same draft.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, type BuildingJson, type ChatStep, type DraftState, type FloorReference, type Op, type Plan, type Proposal } from '../api'
import type { Message, Suggestion } from '../building/Guide'
import { addStep, settle, type Step } from '../ui/guideSteps'
import { placeOps, REACH_PX } from './place'
import { ITEM_PRESETS } from './presets'
import type { XY } from './geometry'
import type { ItemPreset, Selection, Tool } from './types'

const draftKey = (base: string) => `draft:${base}`
const MESSAGE_MS = 6000
const ROTATE_STEP_DEG = 15
export const TOOL_KEYS: Record<string, Tool> = { v: 'select', d: 'door', i: 'item', a: 'access' }

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

/** "422 /drafts/x/ops: {"detail":"…"}" → "…" */
function reason(error: unknown) {
  const text = String(error instanceof Error ? error.message : error)
  const match = text.match(/"detail":\s*"((?:[^"\\]|\\.)*)"/)
  return match ? JSON.parse(`"${match[1]}"`) : text.replace(/^Error:\s*/, '')
}

/** The one door, item or room an edit added, so it can be selected right away. */
function added(before: BuildingJson, after: BuildingJson): Selection {
  for (const [key, kind] of [['openings', 'opening'], ['assets', 'asset'], ['spaces', 'space']] as const) {
    const old = new Set(before[key].map((item) => item.id))
    const fresh = after[key].filter((item) => !old.has(item.id))
    if (fresh.length === 1) return { kind, id: fresh[0].id }
  }
  return null
}

const exists = (building: BuildingJson, selection: Selection) =>
  !selection || (selection.kind === 'space' ? building.spaces : selection.kind === 'opening' ? building.openings : building.assets)
    .some((item) => item.id === selection.id)

const typing = (target: EventTarget | null) =>
  target instanceof HTMLInputElement || target instanceof HTMLSelectElement || target instanceof HTMLTextAreaElement

/** `accessTool`: the Access tool is offered (access mode, the admin) — its key does nothing otherwise. */
export function useDraft(base: string, active: boolean, accessTool = false) {
  const [state, setState] = useState<DraftState | null>(null)
  const [plan, setPlan] = useState<Plan | null>(null)
  const [references, setReferences] = useState<FloorReference[]>([]) // the import's plans, per floor
  const [selected, setSelected] = useState<Selection>(null)
  const [message, setMessage] = useState<string | null>(null)
  // the copy could not be made or resumed (e.g. not the admin): stays until editing starts again, unlike `message`
  const [failed, setFailed] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [revision, setRevision] = useState(0) // bumped on every op response, applied or refused
  const [proposal, setProposal] = useState<Proposal | null>(null) // the Builder's open proposal, drawn as a ghost
  const [tool, setTool] = useState<Tool>('select')
  const [preset, setPreset] = useState<ItemPreset>(ITEM_PRESETS[0])
  const [messages, setMessages] = useState<Message[]>([]) // the conversation with the Builder
  const [asking, setAsking] = useState(false)
  // redo: the ops of the newest steps made here (newest last), and the steps undone since (newest last)
  const history = useRef<Op[][]>([])
  const [redoable, setRedoable] = useState<Op[][]>([])
  // a step count we did not make ourselves: forget what we knew
  const known = (next: DraftState, ops: Op[] | null, before: number) => {
    if (ops && next.draft.steps === before + 1) history.current = [...history.current, ops].slice(-next.draft.steps)
    else if (next.draft.steps !== before) history.current = []
  }

  // Open (or resume) the draft when editing starts.
  useEffect(() => {
    if (!active) return
    let cancelled = false
    setFailed(null)
    openDraft(base).then((next) => !cancelled && setState(next)).catch((error) => !cancelled && setFailed(reason(error)))
    return () => {
      cancelled = true
    }
  }, [base, active])

  // The model follows every change.
  const draftId = state?.draft.id
  useEffect(() => {
    if (!draftId || !active) return
    let cancelled = false
    api.draftPlan(draftId).then((next) => !cancelled && setPlan(next)).catch(() => {})
    return () => {
      cancelled = true
    }
  }, [draftId, state, active])

  // The import's straightened plans (Edit mode's reference panel and trace): per draft, again when floors come or go
  // ("Add a floor", its undo).
  const floorCount = state?.building.floors.length
  const [referenceRevision, setReferenceRevision] = useState(0) // the trace moved (set_reference) or a step was undone
  const touchesReference = (ops: Op[]) => ops.some((item) => item.op === 'set_reference')
  useEffect(() => {
    if (!draftId || !active) return
    let cancelled = false
    api.draftReferences(draftId).then((next) => !cancelled && setReferences(next)).catch(() => !cancelled && setReferences([]))
    return () => {
      cancelled = true
    }
  }, [draftId, active, floorCount, referenceRevision])

  // A message goes away by itself.
  useEffect(() => {
    if (!message) return
    const timer = setTimeout(() => setMessage(null), MESSAGE_MS)
    return () => clearTimeout(timer)
  }, [message])

  const run = useCallback(async (work: () => Promise<DraftState>, after?: (next: DraftState) => void) => {
    setBusy(true)
    const before = state?.building
    try {
      const next = await work()
      after?.(next)
      setState(next)
      setMessage(null)
      // something new (a door or item just placed) is selected so you can adjust it; something gone is unselected
      const fresh = before ? added(before, next.building) : null
      if (fresh) {
        setSelected(fresh)
        setTool('select')
      } else setSelected((current) => (exists(next.building, current) ? current : null))
    } catch (error) {
      setMessage(reason(error))
      // 409: the draft moved on elsewhere (another tab or server instance) — show where it is now.
      if (draftId && String(error).includes('409 ')) {
        const latest = await api.draft(draftId).catch(() => null)
        if (latest) {
          setState(latest)
          history.current = []
          setRedoable([])
        }
      }
    } finally {
      setBusy(false)
      setRevision((value) => value + 1)
    }
  }, [draftId, state])

  // A hand edit makes an open proposal stale (the backend would refuse it), so it is dropped.
  const onOps = useCallback((ops: Op[]) => {
    if (!draftId || busy) return
    setProposal(null)
    const steps = state?.draft.steps ?? 0
    void run(() => api.applyOps(draftId, ops), (next) => {
      known(next, ops, steps)
      if (touchesReference(ops)) setReferenceRevision((n) => n + 1)
      setRedoable([])
    })
  }, [draftId, busy, run, state])

  const undo = useCallback(() => {
    if (!draftId || busy || !state || state.draft.steps === 0) return
    setProposal(null)
    const undone = history.current.at(-1)
    void run(() => api.undo(draftId), () => {
      history.current = history.current.slice(0, -1)
      if (!undone || touchesReference(undone)) setReferenceRevision((n) => n + 1)
      // a step made before this tab knew it can be undone, but not redone
      setRedoable((stack) => (undone ? [...stack, undone] : []))
    })
  }, [draftId, busy, state, run])

  const redo = useCallback(() => {
    const ops = redoable.at(-1)
    if (!draftId || busy || !ops) return
    setProposal(null)
    const steps = state?.draft.steps ?? 0
    void run(() => api.applyOps(draftId, ops), (next) => {
      known(next, ops, steps)
      if (touchesReference(ops)) setReferenceRevision((n) => n + 1)
      setRedoable((stack) => stack.slice(0, -1))
    })
  }, [draftId, busy, state, run, redoable])

  /** The Door / Item tool's tap at `at` on a floor (PlanView onTap). False when there was nothing to put it on. */
  const placeAt = useCallback((floorId: string, at: XY, pixelsPerMetre: number) => {
    if (!state || busy || (tool !== 'door' && tool !== 'item')) return false
    const ops = placeOps(state.building, floorId, at, tool, preset, REACH_PX / Math.max(pixelsPerMetre, 1e-6))
    if (!ops) {
      setMessage(tool === 'door' ? 'Tap closer to a wall to put a door in it.' : 'Tap inside a room to put the item there.')
      return false
    }
    onOps(ops)
    return true
  }, [state, busy, tool, preset, onOps])

  /** Start over: a fresh copy of the original building (the old draft is left behind, not deleted). */
  const discard = useCallback(async () => {
    if (busy) return
    setBusy(true)
    try {
      const created = await api.createDraft(base)
      localStorage.setItem(draftKey(base), created.draft.id)
      setState(created)
      setSelected(null)
      setProposal(null)
      setMessages([])
      history.current = []
      setRedoable([])
      setTool('select')
    } catch (error) {
      setMessage(reason(error))
    } finally {
      setBusy(false)
      setRevision((value) => value + 1)
    }
  }, [base, busy])

  const deleteSelected = useCallback(() => {
    if (!selected) return
    onOps([selected.kind === 'space' ? { op: 'delete_space', space_id: selected.id }
      : selected.kind === 'opening' ? { op: 'delete_opening', opening_id: selected.id }
      : { op: 'delete_asset', asset_id: selected.id }])
  }, [selected, onOps])

  const turnSelected = useCallback((step: number) => {
    const asset = selected?.kind === 'asset' ? state?.building.assets.find((item) => item.id === selected.id) : undefined
    if (asset) onOps([{ op: 'move_asset', asset_id: asset.id, position: asset.position, rotation_deg: asset.footprint.rotation_deg + step }])
  }, [selected, state, onOps])

  /** One Builder turn: its tool steps show as the card's work trail; a proposal is drawn on the model and waits for
   * Apply (or a "yes"). `speak` reads the reply aloud (a spoken or tapped request); `idle` ends the voice loop on failure. */
  const ask = async (text: string, voice: { spoken?: boolean; speak?: (text: string) => void; idle?: () => void } = {}) => {
    if (!draftId || asking) return
    const spoken = Boolean(voice.spoken)
    setMessages((list) => [...list, { role: 'user', text, spoken }, { role: 'guide', text: '', live: true }])
    setAsking(true)
    let key = 0
    const onLive = (update: (steps: Step[]) => Step[]) =>
      setMessages((list) => list.map((item) => (item.role === 'guide' && item.live ? { ...item, steps: update(item.steps ?? []) } : item)))
    try {
      const open = proposal
      const steps = state?.draft.steps ?? 0
      const reply = await api.builderStream(draftId, text, (step) => onLive((steps) => addStep(steps, step as ChatStep, key++)))
      // a "yes" applied the open proposal: its ops are the new step
      known(reply.state, open?.ops ?? null, steps)
      if (reply.state.draft.steps !== steps) setRedoable([])
      setMessages((list) => list.map((item) =>
        item.role === 'guide' && item.live ? { role: 'guide', text: reply.reply, spoken, steps: settle(item.steps ?? []) } : item))
      setState(reply.state)
      setProposal(reply.proposal)
      setRevision((value) => value + 1)
      voice.speak?.(reply.reply)
    } catch (error) {
      setMessages((list) => [...list.filter((item) => !(item.role === 'guide' && item.live)), { role: 'note', text: `The Builder could not answer: ${reason(error)}` }])
      voice.idle?.()
    } finally {
      setAsking(false)
    }
  }

  const apply = async () => {
    if (!draftId || !proposal) return
    setBusy(true)
    try {
      const steps = state?.draft.steps ?? 0
      const next = await api.applyProposal(draftId, proposal.id)
      known(next, proposal.ops, steps)
      setRedoable([])
      setState(next)
      setMessages((list) => [...list, { role: 'guide', text: `Done — ${proposal.summary.replace(/^\w/, (c) => c.toLowerCase())}.` }])
    } catch (error) {
      setMessages((list) => [...list, { role: 'note', text: `Not applied: ${reason(error)}` }])
    } finally {
      setProposal(null)
      setBusy(false)
      setRevision((value) => value + 1)
    }
  }

  // Cancel closes the proposal on the server too, so a later "yes" can't apply it.
  const cancel = () => {
    if (draftId && proposal) void api.cancelProposal(draftId, proposal.id).catch(() => {})
    setProposal(null)
  }

  // starter requests built from this building's own rooms
  const suggestions = useMemo((): Suggestion[] => {
    const rooms = (state?.building.spaces ?? []).filter((space) => space.type === 'room' && space.ref)
    if (rooms.length < 2) return []
    return [
      { label: `Rename ${rooms[1].ref}`, prompt: `Rename ${rooms[1].ref} to Quiet room`, icon: 'edit' },
      { label: `Widen ${rooms[0].ref}`, prompt: `Make ${rooms[0].ref} 1 m wider to the east`, icon: 'edit' },
      { label: 'Add a door', prompt: `Add a door between ${rooms[0].ref} and ${rooms[1].ref}`, icon: 'edit' },
    ]
  }, [state])

  // the floor the open proposal changes, so the screen can show it
  const proposalFloorId = useMemo(() => {
    if (!proposal || !state) return null
    const before = state.building
    const after = proposal.building
    const changed = (key: 'spaces' | 'openings' | 'assets') =>
      after[key].find((item) => JSON.stringify(item) !== JSON.stringify((before[key] as { id: string }[]).find((old) => old.id === item.id)))
    return (changed('spaces') ?? changed('openings') ?? changed('assets'))?.floor_id ?? null
  }, [proposal, state])

  const save = async (name: string): Promise<string | null> => {
    if (!draftId) return null
    setBusy(true)
    try {
      const saved = await api.saveDraft(draftId, name)
      localStorage.removeItem(draftKey(base))
      return saved.building
    } catch (error) {
      setMessage(reason(error))
      setBusy(false)
      return null
    }
  }

  // ⌘Z undo · V / D / I tools · Delete removes the selection · R / Shift+R turns an item · Escape steps back
  useEffect(() => {
    if (!active) return
    const onKey = (event: KeyboardEvent) => {
      const key = event.key.toLowerCase()
      if ((event.metaKey || event.ctrlKey) && !typing(event.target) && (key === 'z' || key === 'y')) {
        event.preventDefault()
        if (key === 'y' || event.shiftKey) redo()
        else undo()
        return
      }
      if (event.metaKey || event.ctrlKey || event.altKey || typing(event.target)) return
      if (TOOL_KEYS[key] && (TOOL_KEYS[key] !== 'access' || accessTool)) setTool(TOOL_KEYS[key])
      else if ((key === 'delete' || key === 'backspace') && selected && tool !== 'access') {
        event.preventDefault()
        deleteSelected()
      } else if (key === 'r' && selected?.kind === 'asset' && !busy) turnSelected(event.shiftKey ? -ROTATE_STEP_DEG : ROTATE_STEP_DEG)
      else if (key === 'escape') {
        if (tool !== 'select') setTool('select')
        else setSelected(null)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [active, undo, redo, deleteSelected, turnSelected, selected, tool, busy, accessTool])

  // leaving the Edit mode drops the transient bits; the draft itself is kept
  useEffect(() => {
    if (active) return
    setSelected(null)
    setTool('select')
    setProposal(null)
  }, [active])

  // a state changed outside the ops above (the map placement, PUT /drafts/{id}/location): one more undoable step
  const adopt = (next: DraftState) => {
    known(next, null, state?.draft.steps ?? 0)
    setRedoable([])
    setState(next)
  }

  return {
    adopt, state, plan, references, selected, setSelected, message, setMessage, failed, busy, revision, proposal, tool, setTool,
    preset, setPreset, onOps, undo, redo, canRedo: redoable.length > 0, placeAt, discard, deleteSelected, turnSelected, save,
    messages, setMessages, asking, ask, apply, cancel, suggestions, proposalFloorId,
  }
}

export type Draft = ReturnType<typeof useDraft>
