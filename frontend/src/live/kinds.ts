// What the living building's things look like and how they are named (./LiveLayer.tsx, ./LivePanel.tsx).

import { Bot, BrushCleaning, Forklift, Package, Radio, ShoppingCart, Truck } from 'lucide-react'
import type { LiveDevice, LiveKind } from '../api'

export const KIND_ICON: Record<LiveKind, typeof Bot> = {
  forklift: Forklift,
  agv: Truck,
  delivery_robot: Bot,
  cleaning_robot: BrushCleaning,
  pallet: Package,
  pallet_jack: Package,
  cart: ShoppingCart,
  device: Radio,
}

export const tone = (item: LiveDevice) => (item.blocking ? 'block' : item.moving ? 'moving' : 'idle')

const STATE_LABEL: Record<string, string> = {
  moving: 'moving',
  cleaning: 'cleaning',
  loading: 'loading',
  unloading: 'unloading',
  riding: 'in the lift',
  idle: 'waiting',
  parked: 'parked',
  'left behind': 'left here',
}
export const stateLabel = (state: string) => STATE_LABEL[state] ?? state
export const ago = (seconds: number) => (seconds < 1.5 ? 'just now' : seconds < 90 ? `${Math.round(seconds)} s ago` : `${Math.round(seconds / 60)} min ago`)
