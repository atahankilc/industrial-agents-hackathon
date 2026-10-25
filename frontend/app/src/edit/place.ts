// Where the Door and Item tools put things (building metres, x east, y north): the hover ghost (EditLayer) and the
// tap that places (BuildingScreen, from PlanView's onTap) use the same rule, so what you see is what you get.

import type { BuildingJson, Op } from '../api'
import { inside, nearestEdge, round3, samePoint, type XY } from './geometry'
import type { ItemPreset, Tool } from './types'

export const DOOR_WIDTH_M = 0.9
const WALL_GAP_M = 0.6 // the other side of a wall is at most this much farther than the near side
export const REACH_PX = 18 // the Door tool finds a wall this close to the pointer

export type DoorSpot = { spaceIds: string[]; position: XY; a: XY; b: XY }

const spacesOn = (building: BuildingJson, floorId: string) => building.spaces.filter((space) => space.floor_id === floorId)

/** The wall within `reach` metres of `p` and the spaces on its two sides (one side only: an outer wall, an entrance). */
export function doorSpot(building: BuildingJson, floorId: string, p: XY, reach: number): DoorSpot | null {
  const near = spacesOn(building, floorId)
    .map((space) => ({ space, ...nearestEdge(p, space.polygon as XY[]) }))
    .sort((u, v) => u.distance - v.distance)
  const first = near[0]
  if (!first || first.distance > reach) return null
  // the other side must face this wall along its length: a neighbour whose nearest point is one of its corners only
  // touches the wall end to end (two rooms along an outer wall), and the door would land on their shared wall
  const second = near.find((hit) => hit.space.id !== first.space.id && hit.distance <= first.distance + WALL_GAP_M &&
    !samePoint(hit.point, hit.a) && !samePoint(hit.point, hit.b))
  const position: XY = second
    ? [round3((first.point[0] + second.point[0]) / 2), round3((first.point[1] + second.point[1]) / 2)]
    : [round3(first.point[0]), round3(first.point[1])]
  return { spaceIds: [first.space.id, second ? second.space.id : 'outside'], position, a: first.a, b: first.b }
}

export const roomAt = (building: BuildingJson, floorId: string, p: XY) =>
  spacesOn(building, floorId).find((space) => inside(p, space.polygon as XY[])) ?? null

/** The op the Door / Item tool makes for a tap at `p`, or null when there is nothing to put it on. */
export function placeOps(building: BuildingJson, floorId: string, p: XY, tool: Tool, preset: ItemPreset, reach: number): Op[] | null {
  if (tool === 'door') {
    const spot = doorSpot(building, floorId, p, reach)
    return spot ? [{ op: 'add_opening', space_ids: spot.spaceIds, position: spot.position, kind: 'door', width_m: DOOR_WIDTH_M }] : null
  }
  if (tool === 'item') {
    const room = roomAt(building, floorId, p)
    return room ? [{
      op: 'add_asset', space_id: room.id, name: preset.label, category: preset.category, type: preset.type,
      position: [round3(p[0]), round3(p[1])], footprint: { width_m: preset.width_m, depth_m: preset.depth_m, rotation_deg: 0 },
    }] : null
  }
  return null
}
