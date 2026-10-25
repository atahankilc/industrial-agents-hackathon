// Shared Edit mode types.

export type Selection = { kind: 'space' | 'opening' | 'asset'; id: string } | null
export type Tool = 'select' | 'door' | 'item'
/** An item the Item tool places (core/edits.add_asset). */
export type ItemPreset = { label: string; category: string; type: string; width_m: number; depth_m: number }
