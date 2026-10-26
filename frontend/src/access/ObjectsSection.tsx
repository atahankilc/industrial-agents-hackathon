// Building settings → Objects (access mode, admin): the building's moving objects (backend/api/fleet.py), one card each
// with where it is and its mission — Send to… (a searchable list of the spaces), cancel the mission, delete (asks
// once more); "New object" opens the form (kind as one-tap choices, the measured width, how it may move, room
// types it avoids — this building's own offered), "Import forklifts" turns the building's forklifts into objects.
// A new object's device token shows once, with the simulator command. Same inset groups as the other tabs
// (./BuildingSettings.tsx, styles in ./access.css).

import { Bot, Box, Check, Copy, Forklift, KeyRound, MapPin, Navigation, Plus, ShoppingCart, Trash2, Truck, X, type LucideIcon } from 'lucide-react'
import { useMemo, useState, type FormEvent } from 'react'
import { api, apiUrl, type DispatchResult, type FleetObject, type ObjectKind, type Plan } from '../api'
import { GroupChips } from './Sheet'

const KINDS: ObjectKind[] = ['forklift', 'robot', 'agv', 'cart', 'other']
const KIND_LABEL: Record<ObjectKind, string> = { forklift: 'Forklift', robot: 'Robot', agv: 'AGV', cart: 'Cart', other: 'Other' }
const KIND_ICON: Record<ObjectKind, LucideIcon> = { forklift: Forklift, robot: Bot, agv: Truck, cart: ShoppingCart, other: Box }
const message = (reason: unknown) => (reason instanceof Error ? reason.message : String(reason))
const PLACES_SHOWN = 12

type Created = { id: string; name: string; token: string }

export function ObjectsSection({ buildingId, plan, objects, onChanged }: { buildingId: string; plan: Plan | null; objects: FleetObject[]; onChanged: () => void }) {
  const [created, setCreated] = useState<Created[]>([])
  const [error, setError] = useState<string | null>(null)
  const [importing, setImporting] = useState(false)
  const [adding, setAdding] = useState(false)
  const hasForklifts = Boolean(plan?.assets.some((asset) => asset.type === 'forklift'))
  const spaceName = (id: string | null | undefined) => (id ? plan?.spaces.find((space) => space.id === id)?.name ?? id : null)
  const roomTypes = useMemo(() => [...new Set((plan?.spaces ?? []).map((space) => space.room_type).filter(Boolean))].sort(), [plan])

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
    <>
      <h4>Moving objects{objects.length ? ` · ${objects.length}` : ''}</h4>
      <div className="pref-group tone-route">
        {objects.length === 0 && (
          <div className="pref-row">
            <span className="pref-label">
              <i className="pref-icon" aria-hidden="true"><Forklift size={20} strokeWidth={1.9} /></i>
              <span>No objects yet<small>Forklifts, robots and other vehicles: each reports its position with its own token and takes missions.</small></span>
            </span>
          </div>
        )}
        {objects.map((item) => (
          <ObjectRow key={item.id} item={item} plan={plan} spaceName={spaceName} onChanged={onChanged} />
        ))}
      </div>
      {error && <p className="sheet-error" role="alert">{error}</p>}

      {created.length > 0 && <Tokens created={created} onClose={() => setCreated([])} />}

      {adding ? (
        <NewObject buildingId={buildingId} roomTypes={roomTypes} onClose={() => setAdding(false)} onCreated={(item) => {
          setAdding(false)
          remember([item])
        }} />
      ) : (
        <div className="settings-actions">
          <button type="button" className="settings-button" onClick={() => setAdding(true)}>
            <Plus size={16} strokeWidth={2.2} /> New object
          </button>
          {hasForklifts && (
            <button type="button" className="settings-button quiet" onClick={() => void importForklifts()} disabled={importing}>
              <Forklift size={16} strokeWidth={2} /> {importing ? 'Importing…' : 'Import forklifts'}
            </button>
          )}
        </div>
      )}
    </>
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
  const Icon = KIND_ICON[item.kind] ?? Box
  const where = item.position ? spaceName(item.position.space_id) ?? 'Outside the rooms' : 'No position yet'
  const status = !mission ? null : mission.status === 'active' ? `On the way to ${mission.to.name} · ${Math.round(mission.length_m)} m` : mission.status === 'done' ? `Arrived at ${mission.to.name}` : `Mission to ${mission.to.name} cancelled`

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
    <div className="pref-row settings-area object-row">
      <span className="pref-label">
        <i className="pref-icon" aria-hidden="true"><Icon size={20} strokeWidth={1.9} /></i>
        <span>
          {item.name}
          <small>{KIND_LABEL[item.kind] ?? item.kind} · {item.attributes.width_m} m wide</small>
        </span>
        {deleting ? (
          <span className="object-confirm">
            <button type="button" className="object-chip danger" onClick={() => void act(() => api.deleteObject(item.id))} disabled={busy}>Delete</button>
            <button type="button" className="object-chip" onClick={() => setDeleting(false)}>Keep</button>
          </span>
        ) : (
          <button type="button" className="hud-icon settings-remove" onClick={() => setDeleting(true)} aria-label={`Delete ${item.name}`} title="Delete">
            <Trash2 size={15} strokeWidth={2} />
          </button>
        )}
      </span>
      <div className="object-status">
        <p className={item.position ? '' : 'none'}><MapPin size={13} strokeWidth={2} aria-hidden="true" />{where}</p>
        {status && <p className={mission?.status === 'active' ? 'live' : ''}><Navigation size={13} strokeWidth={2} aria-hidden="true" />{status}</p>}
      </div>
      <div className="object-actions">
        <button type="button" className="object-chip" onClick={() => setSending((open) => !open)} disabled={busy || !item.position}
          title={item.position ? undefined : 'It has not reported a position yet'}>
          {sending ? <><X size={13} strokeWidth={2.2} /> Close</> : <><Navigation size={13} strokeWidth={2.2} /> Send to…</>}
        </button>
        {mission?.status === 'active' && (
          <button type="button" className="object-chip" onClick={() => void act(() => api.cancelMission(item.id))} disabled={busy}>
            Cancel mission
          </button>
        )}
      </div>
      {sending && plan && <PlacePicker plan={plan} onPick={(id) => void dispatch(id)} />}
      {result && <p className="sheet-error" role="alert">{result}</p>}
    </div>
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
    <div className="settings-search place-picker">
      <label className="settings-search-field">
        <MapPin size={16} strokeWidth={2} aria-hidden="true" />
        <input type="text" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Where to? A room, number or type" autoFocus aria-label="Destination" />
      </label>
      <ul>
        {matches.slice(0, PLACES_SHOWN).map((space) => (
          <li key={space.id}>
            <button type="button" onClick={() => onPick(space.id)}>
              <MapPin size={16} strokeWidth={1.9} aria-hidden="true" />
              <span>{space.name}<small>{[space.ref, plan.floors[space.floor]?.name].filter(Boolean).join(' · ')}</small></span>
            </button>
          </li>
        ))}
      </ul>
      {matches.length > PLACES_SHOWN && <p className="sheet-hint">{matches.length - PLACES_SHOWN} more — type more of the name.</p>}
      {matches.length === 0 && <p className="sheet-hint">No space matches.</p>}
    </div>
  )
}

/** Device tokens, shown once, with the simulator command. */
function Tokens({ created, onClose }: { created: Created[]; onClose: () => void }) {
  return (
    <div className="settings-invite tokens">
      <div className="settings-invite-head">
        <h4><KeyRound size={13} strokeWidth={2.2} aria-hidden="true" /> New device tokens</h4>
        <button type="button" className="hud-icon" onClick={onClose} aria-label="Hide the tokens"><X size={15} strokeWidth={2} /></button>
      </div>
      <p className="sheet-hint">Shown only now — copy them. Each object posts its position with its token; the simulator drives one along its missions.</p>
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

function NewObject({ buildingId, roomTypes, onCreated, onClose }: { buildingId: string; roomTypes: string[]; onCreated: (item: FleetObject) => void; onClose: () => void }) {
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
    } catch (reason) {
      setError(message(reason))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="sheet-form settings-invite new-object" onSubmit={submit}>
      <div className="settings-invite-head">
        <h4>New object</h4>
        <button type="button" className="hud-icon" onClick={onClose} aria-label="Close the form"><X size={15} strokeWidth={2} /></button>
      </div>
      <div className="object-kinds" role="radiogroup" aria-label="Kind">
        {KINDS.map((value) => {
          const Icon = KIND_ICON[value]
          return (
            <button key={value} type="button" role="radio" aria-checked={kind === value} onClick={() => setKind(value)}>
              <Icon size={18} strokeWidth={1.9} />
              <span>{KIND_LABEL[value]}</span>
            </button>
          )
        })}
      </div>
      <div className="object-fields">
        <label className="field">
          <span>Name</span>
          <input type="text" value={name} onChange={(event) => setName(event.target.value)} required autoComplete="off" autoFocus placeholder={`e.g. ${KIND_LABEL[kind]} 1`} />
        </label>
        <label className="field unit">
          <span>Width</span>
          <input type="number" inputMode="decimal" min={0.1} max={20} step={0.05} value={width} onChange={(event) => setWidth(event.target.value)} required placeholder="0.8" />
          <em>m</em>
        </label>
      </div>
      <div className="object-moves">
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
      </div>
      <div className="field">
        <span>Room types it avoids</span>
        <GroupChips label="Room types the object avoids" placeholder="e.g. lab" groups={avoid} suggestions={roomTypes}
          onChange={(rooms) => setAvoid([...new Set(rooms.map((room) => room.replace(/\s+/g, '_')))])} />
      </div>
      {error && <p className="sheet-error" role="alert">{error}</p>}
      <button type="submit" className="hud-primary" disabled={busy || !valid}>
        {busy ? 'Creating…' : 'Create object'}
      </button>
    </form>
  )
}
