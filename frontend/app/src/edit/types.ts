// Shared Edit mode types.

export type Selection = { kind: 'space' | 'opening' | 'asset'; id: string } | null
/** `access`: who may enter which room (access mode, admin only; src/access/AccessCard.tsx) */
export type Tool = 'select' | 'door' | 'item' | 'access'
/** An item the Item tool places (core/edits.add_asset). */
export type ItemPreset = { label: string; category: string; type: string; width_m: number; depth_m: number }
