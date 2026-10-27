// What is selected in the Edit mode, and the changes you can make to it right here: a room's name, number and use;
// a door's width, step-free and kind; an item's name, size and turn; delete any of them. Every change is one op
// (backend/core/edits.py set_space / set_opening / set_asset / move_asset / delete_*), so Undo takes it back.
// With nothing selected it says what you can do, and with the Item tool it is the item picker.

import { DoorOpen, Minus, MousePointer2, Package, Plus, RotateCcw, RotateCw, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { AssetJson, BuildingJson, OpeningJson, Op, SpaceJson } from '../api'
import { CATEGORY_LABEL } from '../plan/palette'
import { area, type XY } from './geometry'
import type { ItemPreset, Selection, Tool } from './types'
import { ITEM_PRESETS } from './presets'

const ROTATE_STEP_DEG = 15
const WIDTH_STEP_M = 0.1
const humanise = (value: string) => value.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())
const metres = (value: number) => `${value.toFixed(2).replace(/\.?0+$/, '')} m`

type Props = {
  building: BuildingJson
  selected: Selection
  tool: Tool
  preset: ItemPreset
  onPreset: (preset: ItemPreset) => void
  onOps: (ops: Op[]) => void
  onSelect: (selection: Selection) => void
  busy: boolean
  revision: number
}

export function Inspector({ building, selected, tool, preset, onPreset, onOps, onSelect, busy, revision }: Props) {
  if (tool === 'item') return <ItemPicker preset={preset} onPreset={onPreset} />
  if (tool === 'door') {
    return (
      <Intro icon={<DoorOpen size={16} />} title="Add a door">
        Point at a wall between two rooms — a door appears under the pointer. Click to add it. On an outside wall it
        becomes an entrance.
      </Intro>
    )
  }
  const space = selected?.kind === 'space' ? building.spaces.find((item) => item.id === selected.id) : undefined
  const opening = selected?.kind === 'opening' ? building.openings.find((item) => item.id === selected.id) : undefined
  const asset = selected?.kind === 'asset' ? building.assets.find((item) => item.id === selected.id) : undefined
  const common = { building, onOps, onSelect, busy, revision }
  if (space) return <RoomCard key={space.id} space={space} {...common} />
  if (opening) return <DoorCard key={opening.id} opening={opening} {...common} />
  if (asset) return <ItemCard key={asset.id} asset={asset} {...common} />
  return (
    <Intro icon={<MousePointer2 size={16} />} title="Click something on the plan">
      A room to rename it or drag its walls, a door to move or widen it, an item to move or turn it. Every change is
      on a copy and can be undone.
    </Intro>
  )
}

type CardProps = { building: BuildingJson; onOps: (ops: Op[]) => void; onSelect: (selection: Selection) => void; busy: boolean; revision: number }

function Intro({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <div className="inspector intro">
      <p className="inspector-title">{icon}{title}</p>
      <p className="inspector-note">{children}</p>
    </div>
  )
}

/** A text field that sends its value when you press Enter or leave it, and only if it changed. */
function Field({ label, value, onCommit, disabled, placeholder }: {
  label: string; value: string; onCommit: (value: string) => void; disabled: boolean; placeholder?: string
}) {
  const [text, setText] = useState(value)
  useEffect(() => setText(value), [value])
  const commit = () => {
    const next = text.trim()
    if (next && next !== value) onCommit(next)
    else setText(value)
  }
  return (
    <label className="field">
      <span>{label}</span>
      <input
        value={text}
        placeholder={placeholder}
        disabled={disabled}
        onChange={(event) => setText(event.target.value)}
        onBlur={commit}
        onKeyDown={(event) => {
          if (event.key === 'Enter') (event.target as HTMLInputElement).blur()
          if (event.key === 'Escape') {
            setText(value)
            ;(event.target as HTMLInputElement).blur()
          }
        }}
      />
    </label>
  )
}

function Stepper({ label, value, onChange, disabled, min, step }: {
  label: string; value: number; onChange: (value: number) => void; disabled: boolean; min: number; step: number
}) {
  const set = (next: number) => onChange(Math.round(Math.max(min, next) * 100) / 100)
  return (
    <div className="field">
      <span>{label}</span>
      <div className="stepper">
        <button type="button" onClick={() => set(value - step)} disabled={disabled || value - step < min - 1e-9} aria-label={`Less ${label.toLowerCase()}`}>
          <Minus size={14} />
        </button>
        <output>{metres(value)}</output>
        <button type="button" onClick={() => set(value + step)} disabled={disabled} aria-label={`More ${label.toLowerCase()}`}>
          <Plus size={14} />
        </button>
      </div>
    </div>
  )
}

function Delete({ label, onClick, disabled }: { label: string; onClick: () => void; disabled: boolean }) {
  return (
    <button type="button" className="inspector-delete" onClick={onClick} disabled={disabled} title={`${label} (Delete key)`}>
      <Trash2 size={15} /> {label}
    </button>
  )
}

const nameOf = (building: BuildingJson, id: string) => {
  if (id === 'outside') return 'outside'
  const space = building.spaces.find((item) => item.id === id)
  return space ? (space.ref && !space.name.includes(space.ref) ? `${space.ref} ${space.name}` : space.name) : id
}

function RoomCard({ space, building, onOps, busy }: CardProps & { space: SpaceJson }) {
  const doors = building.openings.filter((item) => item.space_ids.includes(space.id)).length
  const items = building.assets.filter((item) => item.space_id === space.id).length
  // the uses on offer: this building's own room types plus the app's known ones, so any value can be kept
  const uses = [...new Set([space.room_type, ...building.spaces.map((item) => item.room_type), ...Object.keys(CATEGORY_LABEL)])]
    .filter(Boolean).sort((a, b) => humanise(a).localeCompare(humanise(b)))
  const set = (fields: Partial<Record<'name' | 'ref' | 'room_type', string>>) => onOps([{ op: 'set_space', space_id: space.id, ...fields }])
  const extra = [doors && `${doors} ${doors === 1 ? 'door' : 'doors'}`, items && `${items} ${items === 1 ? 'item' : 'items'}`].filter(Boolean).join(' and ')
  return (
    <div className="inspector">
      <p className="who">{humanise(space.type)}</p>
      <p className="inspector-name">{space.name}</p>
      <p className="inspector-facts">{area(space.polygon as XY[]).toFixed(1)} m² · {doors} {doors === 1 ? 'door' : 'doors'} · {items} {items === 1 ? 'item' : 'items'}</p>
      <div className="fields">
        <Field label="Name" value={space.name} onCommit={(name) => set({ name })} disabled={busy} />
        <Field label="Number" value={space.ref ?? ''} placeholder="e.g. 0.14" onCommit={(ref) => set({ ref })} disabled={busy} />
        <label className="field">
          <span>Use</span>
          <select value={space.room_type} disabled={busy} onChange={(event) => set({ room_type: event.target.value })}>
            {uses.map((use) => <option key={use} value={use}>{CATEGORY_LABEL[use] ?? humanise(use)}</option>)}
          </select>
        </label>
      </div>
      <p className="inspector-note">Drag a corner or a wall on the plan to reshape it — the rooms next to it follow.</p>
      <Delete label={extra ? `Delete room (and its ${extra})` : 'Delete room'} onClick={() => onOps([{ op: 'delete_space', space_id: space.id }])} disabled={busy} />
    </div>
  )
}

const NARROW_M = 0.8 // the wheelchair / pram presets' min_door_width_m (backend/agents/tools/profile.py PRESETS)
const access = (opening: OpeningJson) =>
  !opening.step_free ? 'It has a step, so step-free routes avoid it. '
  : opening.width_m < NARROW_M ? 'Under 0.8 m: wheelchair and pram routes avoid it. '
  : ''

function DoorCard({ opening, building, onOps, busy }: CardProps & { opening: OpeningJson }) {
  const set = (fields: Record<string, unknown>) => onOps([{ op: 'set_opening', opening_id: opening.id, ...fields }])
  const entrance = opening.space_ids.includes('outside')
  const [from, to] = opening.space_ids.map((id) => nameOf(building, id))
  return (
    <div className="inspector">
      <p className="who">{entrance ? 'Entrance' : opening.kind === 'opening' ? 'Opening' : 'Door'}</p>
      <p className="inspector-name">{from} ↔ {to}</p>
      <div className="fields">
        {!entrance && (
          <div className="field">
            <span>Kind</span>
            <div className="segmented" role="radiogroup" aria-label="Kind">
              {(['door', 'opening'] as const).map((kind) => (
                <button key={kind} type="button" role="radio" aria-checked={opening.kind === kind} disabled={busy}
                  onClick={() => opening.kind !== kind && set({ kind })}>
                  {kind === 'door' ? 'Door' : 'Passage'}
                </button>
              ))}
            </div>
          </div>
        )}
        <Stepper label="Width" value={opening.width_m} min={0.5} step={WIDTH_STEP_M} onChange={(width_m) => set({ width_m })} disabled={busy} />
        <label className="field toggle">
          <span>Step-free</span>
          <input type="checkbox" role="switch" checked={opening.step_free} disabled={busy} onChange={(event) => set({ step_free: event.target.checked })} />
        </label>
      </div>
      <p className="inspector-note">
        {access(opening)}Drag it along its wall on the plan to move it.
      </p>
      <Delete label={entrance ? 'Delete entrance' : 'Delete door'} onClick={() => onOps([{ op: 'delete_opening', opening_id: opening.id }])} disabled={busy} />
    </div>
  )
}

function ItemCard({ asset, building, onOps, busy }: CardProps & { asset: AssetJson }) {
  const turn = (step: number) =>
    onOps([{ op: 'move_asset', asset_id: asset.id, position: asset.position, rotation_deg: asset.footprint.rotation_deg + step }])
  const size = (key: 'width_m' | 'depth_m') => (value: number) => onOps([{ op: 'set_asset', asset_id: asset.id, footprint: { [key]: value } }])
  return (
    <div className="inspector">
      <p className="who">{humanise(asset.category)} · {humanise(asset.type)}</p>
      <p className="inspector-name">{asset.name}</p>
      <p className="inspector-facts">In {nameOf(building, asset.space_id)} · turned {Math.round(asset.footprint.rotation_deg)}°</p>
      <div className="fields">
        <Field label="Name" value={asset.name} onCommit={(name) => onOps([{ op: 'set_asset', asset_id: asset.id, name }])} disabled={busy} />
        <Stepper label="Width" value={asset.footprint.width_m} min={0.1} step={WIDTH_STEP_M} onChange={size('width_m')} disabled={busy} />
        <Stepper label="Depth" value={asset.footprint.depth_m} min={0.1} step={WIDTH_STEP_M} onChange={size('depth_m')} disabled={busy} />
        <div className="field">
          <span>Turn</span>
          <div className="segmented">
            <button type="button" onClick={() => turn(-ROTATE_STEP_DEG)} disabled={busy} aria-label="Turn left" title="Turn left (Shift+R)">
              <RotateCcw size={14} />
            </button>
            <button type="button" onClick={() => turn(ROTATE_STEP_DEG)} disabled={busy} aria-label="Turn right" title="Turn right (R)">
              <RotateCw size={14} />
            </button>
          </div>
        </div>
      </div>
      <p className="inspector-note">Drag it on the plan to move it, even into another room.</p>
      <Delete label="Delete item" onClick={() => onOps([{ op: 'delete_asset', asset_id: asset.id }])} disabled={busy} />
    </div>
  )
}

function ItemPicker({ preset, onPreset }: { preset: ItemPreset; onPreset: (preset: ItemPreset) => void }) {
  return (
    <div className="inspector">
      <p className="inspector-title"><Package size={16} />Add an item</p>
      <p className="inspector-note">Pick what to add, then click inside a room to place it.</p>
      <div className="presets" role="radiogroup" aria-label="Item">
        {ITEM_PRESETS.map((item) => (
          <button key={item.type} type="button" role="radio" aria-checked={item.type === preset.type} onClick={() => onPreset(item)}>
            {item.label}
          </button>
        ))}
      </div>
    </div>
  )
}
