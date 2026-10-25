// Building settings → Objects (access mode, admin): the building's moving objects (backend/fleet.py) with where they
// are and their mission; create one (attributes the data can use, design "Moving objects"), import the building's
// forklifts, show each new device token once with the simulator command, dispatch to a space, cancel, delete.

import { Check, Copy } from 'lucide-react'
import { useMemo, useState, type FormEvent } from 'react'
import { api, apiUrl, type DispatchResult, type FleetObject, type ObjectKind, type Plan } from '../api'
import { GroupChips } from './Sheet'

const KINDS: ObjectKind[] = ['forklift', 'robot', 'agv', 'cart', 'other']
const KIND_LABEL: Record<ObjectKind, string> = { forklift: 'Forklift', robot: 'Robot', agv: 'AGV', cart: 'Cart', other: 'Other' }
const message = (reason: unknown) => (reason instanceof Error ? reason.message : String(reason))
const PLACES_SHOWN = 30

type Created = { id: string; name: string; token: string }

export function ObjectsSection({ buildingId, plan, objects, onChanged }: { buildingId: string; plan: Plan | null; objects: FleetObject[]; onChanged: () => void }) {
  const [created, setCreated] = useState<Created[]>([])
  const [error, setError] = useState<string | null>(null)
  const [importing, setImporting] = useState(false)
  const hasForklifts = Boolean(plan?.assets.some((asset) => asset.type === 'forklift'))
  const spaceName = (id: string | null | undefined) => (id ? plan?.spaces.find((space) => space.id === id)?.name ?? id : null)

  const remember = (items: FleetObject[]) => {
    setCreated((list) => [...items.filter((item) => item.token).map((item) => ({ id: item.id, name: item.name, token: item.token! })), ...list])
    onChanged()
  }
  const importForklifts = async () => {
    setImporting(true)
    setError(null)
    try {
      const items = await api.importForklifts(buildingId)
      if (!items.length) setError('Every forklift of this building is already an object.')
      remember(items)
    } catch (reason) {
      setError(message(reason))
    } finally {
      setImporting(false)
    }
  }

  return (
    <section className="sheet-section">
      <h3>Objects</h3>
      <p className="sheet-hint">Forklifts, robots and other vehicles: each reports its position with its own token and takes missions.</p>
      {objects.length === 0 && <p className="sheet-hint">No objects yet.</p>}
      {objects.length > 0 && (
        <ul className="rule-list">
          {objects.map((item) => (
            <ObjectRow key={item.id} item={item} plan={plan} spaceName={spaceName} onChanged={onChanged} />
          ))}
        </ul>
      )}
      {error && <p className="sheet-error" role="alert">{error}</p>}
      {hasForklifts && (
        <button type="button" className="sheet-quiet bordered" onClick={() => void importForklifts()} disabled={importing}>
          {importing ? 'Importing…' : 'Import forklifts'}
        </button>
      )}
      {created.length > 0 && <Tokens created={created} />}
      <NewObject buildingId={buildingId} onCreated={(item) => remember([item])} />
    </section>
  )
}

function ObjectRow({ item, plan, spaceName, onChanged }: {
  item: FleetObject
  plan: Plan | null
  spaceName: (id: string | null | undefined) => string | null
  onChanged: () => void
}) {
  const [sending, setSending] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [result, setResult] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const mission = item.mission
  const where = item.position ? spaceName(item.position.space_id) ?? 'Outside the rooms' : 'No position yet'
  const status = !mission ? 'No mission' : mission.status === 'active' ? `On the way to ${mission.to.name} · ${Math.round(mission.length_m)} m` : mission.status === 'done' ? `Arrived at ${mission.to.name}` : `Mission to ${mission.to.name} cancelled`

  const act = async (work: () => Promise<unknown>) => {
    setBusy(true)
    setResult(null)
    try {
      await work()
      onChanged()
    } catch (reason) {
      setResult(message(reason))
    } finally {
      setBusy(false)
    }
  }
  const dispatch = (destination: string) =>
    act(async () => {
      const reply: DispatchResult = await api.dispatch(item.id, destination)
      setSending(false)
      setResult(reply.reachable ? null : `Can’t get there: ${reply.reason ?? 'no way that fits it'}`)
    })

  return (
    <li>
      <span className="rule-name">
        {item.name}
        <small>{[KIND_LABEL[item.kind] ?? item.kind, `${item.attributes.width_m} m wide`, where].join(' · ')}</small>
        <small>{status}</small>
      </span>
      <div className="object-actions">
        <button type="button" className="sheet-quiet bordered" onClick={() => setSending((open) => !open)} disabled={busy || !item.position}>
          {sending ? 'Close' : 'Send to…'}
        </button>
        {mission?.status === 'active' && (
          <button type="button" className="sheet-quiet bordered" onClick={() => void act(() => api.cancelMission(item.id))} disabled={busy}>
            Cancel mission
          </button>
        )}
        {deleting ? (
          <>
            <button type="button" className="sheet-quiet bordered danger" onClick={() => void act(() => api.deleteObject(item.id))} disabled={busy}>
              Delete {item.name}
            </button>
            <button type="button" className="sheet-quiet" onClick={() => setDeleting(false)}>Keep</button>
          </>
        ) : (
          <button type="button" className="sheet-quiet" onClick={() => setDeleting(true)}>Delete</button>
        )}
      </div>
      {sending && plan && <PlacePicker plan={plan} onPick={(id) => void dispatch(id)} />}
      {result && <p className="sheet-error" role="alert">{result}</p>}
    </li>
  )
}

/** A searchable list of the plan's spaces. */
function PlacePicker({ plan, onPick }: { plan: Plan; onPick: (spaceId: string) => void }) {
  const [query, setQuery] = useState('')
  const matches = useMemo(() => {
    const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean)
    return plan.spaces.filter((space) => {
      const text = `${space.name} ${space.ref} ${space.room_type} ${plan.floors[space.floor]?.name ?? ''}`.toLowerCase()
      return words.every((word) => text.includes(word))
    })
  }, [plan, query])
  return (
    <div className="place-picker">
      <label className="field">
        <span>Destination</span>
        <input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Name, ref or type" autoFocus />
      </label>
      <ul>
        {matches.slice(0, PLACES_SHOWN).map((space) => (
          <li key={space.id}>
            <button type="button" onClick={() => onPick(space.id)}>
              {space.name}
              <small>{[space.ref, plan.floors[space.floor]?.name].filter(Boolean).join(' · ')}</small>
            </button>
          </li>
        ))}
      </ul>
      {matches.length > PLACES_SHOWN && <p className="sheet-hint">{matches.length - PLACES_SHOWN} more — narrow the search.</p>}
      {matches.length === 0 && <p className="sheet-hint">No space matches.</p>}
    </div>
  )
}

/** Device tokens, shown once, with the simulator command. */
function Tokens({ created }: { created: Created[] }) {
  return (
    <div className="tokens">
      <h4>New device tokens</h4>
      <p className="sheet-hint">Shown only now. Each object posts its position with its token; the simulator drives one along its missions.</p>
      {created.map((item) => (
        <div key={item.id} className="token-item">
          <span className="rule-name">{item.name}</span>
          <CopyLine label={`Token for ${item.name}`} value={item.token} />
          <CopyLine label={`Simulator command for ${item.name}`} value={`uv run python scripts/sim_object.py --api ${apiUrl()} --object ${item.id} --token=${item.token}`} />
        </div>
      ))}
    </div>
  )
}

function CopyLine({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <div className="link-box">
      <div>
        <input readOnly value={value} onFocus={(event) => event.target.select()} aria-label={label} />
        <button
          type="button"
          className="hud-icon"
          aria-label={`Copy: ${label}`}
          onClick={() => navigator.clipboard.writeText(value).then(() => setCopied(true), () => setCopied(false))}
        >
          {copied ? <Check size={15} strokeWidth={2.4} /> : <Copy size={15} strokeWidth={2} />}
        </button>
      </div>
    </div>
  )
}

function NewObject({ buildingId, onCreated }: { buildingId: string; onCreated: (item: FleetObject) => void }) {
  const [name, setName] = useState('')
  const [kind, setKind] = useState<ObjectKind>('robot')
  const [width, setWidth] = useState('')
  const [stepFreeOnly, setStepFreeOnly] = useState(true)
  const [lifts, setLifts] = useState(true)
  const [stairs, setStairs] = useState(false)
  const [avoid, setAvoid] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const widthM = Number(width)
  const valid = name.trim() && width !== '' && widthM > 0 && widthM <= 20

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!valid) return
    setBusy(true)
    setError(null)
    try {
      const item = await api.createObject(buildingId, name.trim(), kind, {
        width_m: widthM, step_free_only: stepFreeOnly, can_use_lifts: lifts, can_use_stairs: stairs, avoid_room_types: avoid,
      })
      onCreated(item)
      setName('')
      setWidth('')
      setAvoid([])
    } catch (reason) {
      setError(message(reason))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="sheet-form invite" onSubmit={submit}>
      <h4>New object</h4>
      <label className="field">
        <span>Name</span>
        <input type="text" value={name} onChange={(event) => setName(event.target.value)} required autoComplete="off" />
      </label>
      <label className="field">
        <span>Kind</span>
        <select value={kind} onChange={(event) => setKind(event.target.value as ObjectKind)}>
          {KINDS.map((item) => <option key={item} value={item}>{KIND_LABEL[item]}</option>)}
        </select>
      </label>
      <label className="field">
        <span>Width (m)</span>
        <input type="number" inputMode="decimal" min={0.1} max={20} step={0.05} value={width} onChange={(event) => setWidth(event.target.value)} required placeholder="Measured width" />
      </label>
      <label className="toggle-row">
        <span>Step-free only<small>Wheels: no steps or stairs.</small></span>
        <input type="checkbox" role="switch" checked={stepFreeOnly} onChange={(event) => setStepFreeOnly(event.target.checked)} />
      </label>
      <label className="toggle-row">
        <span>Can use lifts</span>
        <input type="checkbox" role="switch" checked={lifts} onChange={(event) => setLifts(event.target.checked)} />
      </label>
      <label className="toggle-row">
        <span>Can use stairs<small>Legged robots.</small></span>
        <input type="checkbox" role="switch" checked={stairs} onChange={(event) => setStairs(event.target.checked)} />
      </label>
      <div className="field">
        <span>Rooms to avoid</span>
        <GroupChips label="Room types the object avoids" placeholder="e.g. lab" groups={avoid} onChange={(rooms) => setAvoid([...new Set(rooms.map((room) => room.replace(/\s+/g, '_')))])} />
      </div>
      {error && <p className="sheet-error" role="alert">{error}</p>}
      <button type="submit" className="hud-primary" disabled={busy || !valid}>
        {busy ? 'Creating…' : 'Create object'}
      </button>
    </form>
  )
}
