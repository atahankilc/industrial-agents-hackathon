// Map-style pins for the places people look for first: toilets, lifts, stairs, food and the ways in and out.
// They are DOM buttons over the canvas (crisp icons, real focus and tap targets); a tracker inside the scene moves
// them to their projected spot after every rendered frame, so they follow pan, zoom, tilt and turn.

import { useFrame, useThree } from '@react-three/fiber'
import { useEffect } from 'react'
import { ArrowUpDown, Bath, DoorOpen, Footprints, UtensilsCrossed } from 'lucide-react'
import * as THREE from 'three'
import type { Plan } from '../api'
import { toScene } from './geometry'

export type PinKind = 'toilet' | 'lift' | 'stairs' | 'food' | 'entrance'
export type Pin = { key: string; kind: PinKind; label: string; space: string | null; at: [number, number] }

const KIND_BY_ROOM: Record<string, PinKind> = {
  toilet: 'toilet', bathroom: 'toilet', lift: 'lift', stairwell: 'stairs', canteen: 'food', kitchen: 'food',
}
const ICON = { toilet: Bath, lift: ArrowUpDown, stairs: Footprints, food: UtensilsCrossed, entrance: DoorOpen }

export function pinsFor(plan: Plan, floor: number): Pin[] {
  const pins: Pin[] = []
  for (const space of plan.spaces) {
    if (space.floor !== floor) continue
    const kind = space.type === 'lift' ? 'lift' : space.type === 'stair' ? 'stairs' : KIND_BY_ROOM[space.room_type]
    if (kind) pins.push({ key: space.id, kind, label: space.name, space: space.id, at: space.label })
  }
  for (const opening of plan.openings) {
    if (opening.floor !== floor || !opening.entrance) continue
    pins.push({ key: opening.id, kind: 'entrance', label: 'Entrance', space: opening.space, at: opening.position })
  }
  return pins
}

export function Pins({ pins, elements, onPick }: { pins: Pin[]; elements: React.RefObject<Map<string, HTMLElement>>; onPick: (pin: Pin) => void }) {
  return (
    <div className="pins">
      {pins.map((pin) => {
        const Icon = ICON[pin.kind]
        return (
          <button
            key={pin.key}
            type="button"
            className={`pin ${pin.kind}`}
            aria-label={pin.label}
            title={pin.label}
            ref={(node) => {
              if (node) elements.current.set(pin.key, node)
              else elements.current.delete(pin.key)
            }}
            onPointerDown={(event) => event.stopPropagation()}
            onPointerUp={(event) => event.stopPropagation()}
            onClick={() => onPick(pin)}
          >
            <Icon size={14} strokeWidth={2.4} aria-hidden="true" />
          </button>
        )
      })}
    </div>
  )
}

/** Inside the canvas: after each frame, put every pin over its spot (hidden when off screen). */
export function PinTracker({ plan, pins, elements }: { plan: Plan; pins: Pin[]; elements: React.RefObject<Map<string, HTMLElement>> }) {
  const { camera, size, invalidate } = useThree()
  const point = new THREE.Vector3()
  useFrame(() => {
    for (const pin of pins) {
      const node = elements.current.get(pin.key)
      if (!node) continue
      const [X, Z] = toScene(plan, pin.at[0], pin.at[1])
      point.set(X, 0.05, Z).project(camera)
      const x = ((point.x + 1) / 2) * size.width
      const y = ((1 - point.y) / 2) * size.height
      const visible = x > -20 && y > -20 && x < size.width + 20 && y < size.height + 20
      node.style.transform = `translate(${x}px, ${y}px) translate(-50%, -100%)`
      node.style.visibility = visible ? 'visible' : 'hidden'
    }
  })
  // pins are placed on the next frame after the list changes
  useEffect(() => invalidate(), [pins, invalidate])
  return null
}
