// What the Edit mode's Item tool can place: common kit asset types with their usual footprint (data/*/building.json).

import type { ItemPreset } from './types'

export const ITEM_PRESETS: ItemPreset[] = [
  { label: 'Desk', category: 'furniture', type: 'desk', width_m: 1.4, depth_m: 0.7 },
  { label: 'Chair', category: 'furniture', type: 'chair', width_m: 0.5, depth_m: 0.5 },
  { label: 'Shelf', category: 'furniture', type: 'shelf', width_m: 1.0, depth_m: 0.4 },
  { label: 'Plant', category: 'furniture', type: 'plant', width_m: 0.4, depth_m: 0.4 },
  { label: 'Whiteboard', category: 'equipment', type: 'whiteboard', width_m: 1.8, depth_m: 0.1 },
  { label: 'Printer', category: 'equipment', type: 'printer', width_m: 0.6, depth_m: 0.5 },
  { label: 'Coffee machine', category: 'equipment', type: 'coffee_machine', width_m: 0.4, depth_m: 0.4 },
  { label: 'Fire extinguisher', category: 'equipment', type: 'fire_extinguisher', width_m: 0.3, depth_m: 0.3 },
  { label: 'Defibrillator', category: 'equipment', type: 'defibrillator', width_m: 0.4, depth_m: 0.2 },
]
