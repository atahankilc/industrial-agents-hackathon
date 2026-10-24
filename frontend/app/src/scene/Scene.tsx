// Placeholder while the scene is rebuilt from scratch (old version in the gitignored .viz-archive/): same props
// as before so App.tsx keeps compiling, renders an empty backdrop.

import type { PointCloud } from '../api'
import type { SpaceSets } from './BuildingCloud'

export type Focus = { nonce: number; target: [number, number, number]; distance: number }

type Props = {
  cloud: PointCloud
  dark: boolean
  sets: SpaceSets
  floorsOn: boolean[]
  explode: number
  density: number
  emergeKey: number
  route: { vertices: [number, number, number, number][]; key: number } | null
  focus: Focus | null
}

export function Scene({ dark }: Props) {
  return <div className="scene" style={{ position: 'absolute', inset: 0, background: dark ? '#111' : '#f4f2ee' }} />
}
