// Placeholder while the scene is rebuilt from scratch: only the shared types and helpers App.tsx needs.
import type { PointCloud } from '../api'

export type SpaceSets = { highlight: number[]; lost: number[]; closed: number[]; route: number[] }

export function cloudExtent(cloud: PointCloud) {
  const positions = cloud.points.position_cm
  let extent = 1
  for (let i = 0; i < positions.length; i += 3) {
    extent = Math.max(extent, Math.abs(positions[i]) / 100, Math.abs(positions[i + 2]) / 100)
  }
  const top = Math.max(...cloud.floors.map((floor) => floor.elevation_m)) + 3
  return { extent, top }
}
